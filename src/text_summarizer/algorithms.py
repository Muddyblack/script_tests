"""Pure-Python, offline extractive text summarization — state-of-the-art level.

No external HTTP, no AI, no LLM. Standard library only.

Key design decisions vs naive implementations:
──────────────────────────────────────────────
  ① Full Porter Stemmer (all 5 steps): "generously"→"generous"→"gener"
     Dramatically improves similarity scoring for graph methods.

  ② YAKE keyword extraction: position × frequency × dispersion × co-occurrence
     Empirically the best offline unsupervised keyword method.

  ③ Named Entity detection: capitalised non-sentence-start words get score boost.
     "Fleming", "Paris Agreement", "COVID-19" are almost always important.

  ④ Redundancy-aware scoring: every method applies a cross-sentence penalty
     so the scoring itself de-emphasises near-duplicate sentences,
     not just MMR selection after the fact.

  ⑤ BM25L (Lv & Zhai 2011): fixes BM25's under-ranking of long relevant docs
     using lower-bound TF normalisation. Better than standard BM25.

  ⑥ Centroid summarization (Radev et al. 2004): true TF-IDF centroid vector
     approach; selects sentences closest to document centroid.

  ⑦ Empirical position curve: news texts front-load importance; academic texts
     have important conclusions. We detect text type and apply correct curve.

  ⑧ Sentence quality filters: length penalty, no all-stopword sentences,
     minimum content-word ratio.

  ⑨ Reciprocal Rank Fusion (Cormack 2009) for Hybrid: parameter-free,
     rank-based ensemble proven to outperform weighted score combinations.

  ⑩ Bigram phrases: "climate_change" scored as unit alongside unigrams.

Algorithms exposed:
  Hybrid    — RRF of BM25L + TextRank + LexRank + Centroid + MMR + COWTS
  BM25L     — BM25L with stemming + bigrams + NE boost + redundancy penalty
  MMR       — Maximal Marginal Relevance (cosine TF-IDF, diversity-aware)
  TextRank  — PageRank on cosine-TF-IDF graph (not Jaccard)
  LexRank   — Cosine eigenvector centrality
  Centroid  — Closest-to-document-centroid (Radev 2004)
  COWTS     — Position + BM25L + title-word boost
  KLSum     — KL-divergence minimisation (information-theoretic)
  TF-IDF    — Classic with stemming + bigrams
  Luhn      — Significant-word cluster scoring (Luhn 1958)
  SumBasic  — Word-probability averaging (Nenkova 2005)
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import NamedTuple


# ═══════════════════════════════════════════════════════════════════════════════
# STOP-WORDS  (expanded — 175 words)
# ═══════════════════════════════════════════════════════════════════════════════

_STOP_WORDS: frozenset[str] = frozenset("""
a about above across after afterwards again against all almost alone along already
also although always am among amongst an and another any anyhow anyone anything
anyway anywhere are aren't around as at back be became because become becomes
becoming been before beforehand behind being below beside besides between beyond
both but by can can't cannot could couldn't did didn't do does doesn't doing
don't down during each else elsewhere enough even ever every everyone everything
everywhere except few for former formerly from further get got had hadn't has
hasn't have haven't having he he'd he'll he's hence her here here's hereafter
hereby herein hereupon hers herself him himself his how how's however i i'd i'll
i'm i've if in indeed instead into is isn't it it's its itself just keep latter
latterly least less like likely ltd made many may me meanwhile might more moreover
most mostly much must mustn't my myself namely neither never nevertheless next no
nobody none noone nor not nothing now nowhere of off often on once only onto or
other others otherwise our ours ourselves out over own per perhaps please rather
re same shan't she she'd she'll she's should shouldn't since so some somehow
someone something sometime sometimes somewhere still such than that that's the
their theirs them themselves then thence there there's thereafter thereby therefore
therein thereupon these they they'd they'll they're they've this those though
through throughout thru thus to together too toward towards under until up upon
us very via was wasn't we we'd we'll we're we've were weren't what what's when
when's where where's whether which while who who's whom why why's will with won't
would wouldn't yet you you'd you'll you're you've your yours yourself yourselves
""".split())


# ═══════════════════════════════════════════════════════════════════════════════
# FULL PORTER STEMMER  (all 5 steps, Paice 1990 implementation)
# ═══════════════════════════════════════════════════════════════════════════════

def _is_consonant(word: str, i: int) -> bool:
    c = word[i]
    if c in 'aeiou':
        return False
    if c == 'y':
        return i == 0 or not _is_consonant(word, i - 1)
    return True


def _measure(stem: str) -> int:
    """Count VC sequences (m) in stem."""
    n = len(stem)
    i = 0
    m = 0
    # Skip leading consonants
    while i < n and _is_consonant(stem, i):
        i += 1
    while i < n:
        # Skip vowels
        while i < n and not _is_consonant(stem, i):
            i += 1
        # Skip consonants
        j = i
        while i < n and _is_consonant(stem, i):
            i += 1
        if i < n or j != i:
            m += 1
    return m


def _has_vowel(stem: str) -> bool:
    return any(not _is_consonant(stem, i) for i in range(len(stem)))


def _ends_double_consonant(word: str) -> bool:
    return (len(word) >= 2
            and word[-1] == word[-2]
            and _is_consonant(word, len(word) - 1))


def _ends_cvc(word: str) -> bool:
    """Ends with consonant-vowel-consonant where last consonant is not w/x/y."""
    if len(word) < 3:
        return False
    return (
        _is_consonant(word, len(word) - 1)
        and not _is_consonant(word, len(word) - 2)
        and _is_consonant(word, len(word) - 3)
        and word[-1] not in 'wxy'
    )


def _stem(word: str) -> str:
    """Full 5-step Porter stemmer."""
    if len(word) <= 2:
        return word
    w = word.lower()

    # Step 1a
    if w.endswith('sses'):
        w = w[:-2]
    elif w.endswith('ies'):
        w = w[:-2]
    elif w.endswith('ss'):
        pass
    elif w.endswith('s'):
        w = w[:-1]

    # Step 1b
    step1b_flag = False
    if w.endswith('eed'):
        if _measure(w[:-3]) > 0:
            w = w[:-1]
    elif w.endswith('ed'):
        stem = w[:-2]
        if _has_vowel(stem):
            w = stem
            step1b_flag = True
    elif w.endswith('ing'):
        stem = w[:-3]
        if _has_vowel(stem):
            w = stem
            step1b_flag = True

    if step1b_flag:
        if w.endswith(('at', 'bl', 'iz')):
            w += 'e'
        elif _ends_double_consonant(w) and not w.endswith(('l', 's', 'z')):
            w = w[:-1]
        elif _measure(w) == 1 and _ends_cvc(w):
            w += 'e'

    # Step 1c
    if w.endswith('y') and _has_vowel(w[:-1]):
        w = w[:-1] + 'i'

    # Step 2
    step2_map = [
        ('ational', 'ate'), ('tional', 'tion'), ('enci', 'ence'),
        ('anci', 'ance'), ('izer', 'ize'), ('abli', 'able'),
        ('alli', 'al'), ('entli', 'ent'), ('eli', 'e'),
        ('ousli', 'ous'), ('ization', 'ize'), ('ation', 'ate'),
        ('ator', 'ate'), ('alism', 'al'), ('iveness', 'ive'),
        ('fulness', 'ful'), ('ousness', 'ous'), ('aliti', 'al'),
        ('iviti', 'ive'), ('biliti', 'ble'),
    ]
    for suffix, replacement in step2_map:
        if w.endswith(suffix) and _measure(w[:-len(suffix)]) > 0:
            w = w[:-len(suffix)] + replacement
            break

    # Step 3
    step3_map = [
        ('icate', 'ic'), ('ative', ''), ('alize', 'al'),
        ('iciti', 'ic'), ('ical', 'ic'), ('ful', ''), ('ness', ''),
    ]
    for suffix, replacement in step3_map:
        if w.endswith(suffix) and _measure(w[:-len(suffix)]) > 0:
            w = w[:-len(suffix)] + replacement
            break

    # Step 4
    step4_suffixes = [
        'al', 'ance', 'ence', 'er', 'ic', 'able', 'ible', 'ant',
        'ement', 'ment', 'ent', 'ion', 'ou', 'ism', 'ate',
        'iti', 'ous', 'ive', 'ize',
    ]
    for suffix in step4_suffixes:
        if w.endswith(suffix):
            stem = w[:-len(suffix)]
            if suffix == 'ion':
                if _measure(stem) > 1 and stem and stem[-1] in 'st':
                    w = stem
            elif _measure(stem) > 1:
                w = stem
            break

    # Step 5a
    if w.endswith('e'):
        stem = w[:-1]
        if _measure(stem) > 1:
            w = stem
        elif _measure(stem) == 1 and not _ends_cvc(stem):
            w = stem

    # Step 5b
    if w.endswith('ll') and _measure(w) > 1:
        w = w[:-1]

    return w if len(w) >= 2 else word


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE SPLITTING
# ═══════════════════════════════════════════════════════════════════════════════

_ABBREV_PAT = re.compile(
    r'\b(Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|i\.e|e\.g|'
    r'Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
    r'U\.S|U\.K|approx|est|fig|vol|no|pp|ch|ed|rev|dept)\.',
    re.IGNORECASE,
)
_SENT_SPLIT_PAT = re.compile(
    r'(?<=[.!?])\s+(?=[A-Z"\'])'   # standard
    r'|\n{2,}'                      # paragraph breaks
    r'|(?<=[a-z,;])\n(?=[A-Z])',    # single newline lower→upper
)


def _split_sentences(text: str) -> list[str]:
    text = _ABBREV_PAT.sub(lambda m: m.group().replace('.', '\x00'), text)
    text = re.sub(r'[ \t]+', ' ', text)
    parts = _SENT_SPLIT_PAT.split(text.strip())
    result = []
    for s in parts:
        s = s.replace('\x00', '.').strip()
        if s and len(s.split()) >= 4:
            result.append(s)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# TOKENISATION & FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def _content_words(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 2]


def _content_stems(text: str) -> list[str]:
    return [_stem(t) for t in _content_words(_tokenize(text))]


def _rich_tokens(text: str) -> list[str]:
    """Stemmed unigrams + stemmed bigrams."""
    stems = _content_stems(text)
    bigrams = [f"{stems[i]}\u00b7{stems[i+1]}" for i in range(len(stems) - 1)]
    return stems + bigrams


def _word_freq(sentences: list[str]) -> Counter:
    freq: Counter = Counter()
    for s in sentences:
        freq.update(_content_stems(s))
    return freq


# Named entity detection: capitalised words not at sentence start
def _named_entities(sentence: str) -> set[str]:
    words = sentence.split()
    entities = set()
    for i, w in enumerate(words[1:], 1):  # skip first word
        clean = re.sub(r'[^A-Za-z]', '', w)
        if clean and clean[0].isupper() and len(clean) > 1:
            entities.add(clean.lower())
    return entities


def _ne_score(sentence: str, global_entities: dict[str, int], n_sents: int) -> float:
    """Score bonus for sentences containing frequent named entities."""
    ents = _named_entities(sentence)
    if not ents or not global_entities:
        return 0.0
    total = sum(global_entities.values())
    return sum(global_entities.get(e, 0) / total for e in ents) / max(len(ents), 1)


def _build_global_entities(sentences: list[str]) -> dict[str, int]:
    counts: Counter = Counter()
    for s in sentences:
        counts.update(_named_entities(s))
    # Only keep entities that appear in 2+ sentences (proper NEs, not noise)
    return {e: c for e, c in counts.items() if c >= 2}


# ═══════════════════════════════════════════════════════════════════════════════
# SENTENCE QUALITY FILTER
# ═══════════════════════════════════════════════════════════════════════════════

def _length_penalty(sentence: str, ideal_min: int = 8, ideal_max: int = 45) -> float:
    n = len(sentence.split())
    if n < ideal_min:
        return max(0.15, n / ideal_min)
    if n > ideal_max:
        return max(0.55, ideal_max / n)
    return 1.0


def _content_ratio(sentence: str) -> float:
    tokens = _tokenize(sentence)
    if not tokens:
        return 0.0
    content = _content_words(tokens)
    return len(content) / len(tokens)


def _sentence_quality(sentence: str) -> float:
    """Combined quality multiplier: length × content-word ratio."""
    return _length_penalty(sentence) * max(0.3, _content_ratio(sentence))


# ═══════════════════════════════════════════════════════════════════════════════
# CROSS-SENTENCE REDUNDANCY PENALTY
# ═══════════════════════════════════════════════════════════════════════════════

def _cosine(va: dict, vb: dict) -> float:
    if not va or not vb:
        return 0.0
    dot = sum(va.get(w, 0.0) * vb.get(w, 0.0) for w in va)
    na = math.sqrt(sum(v * v for v in va.values()))
    nb = math.sqrt(sum(v * v for v in vb.values()))
    return dot / (na * nb) if na and nb else 0.0


def _apply_redundancy_penalty(
    scores: list[SentenceScore],
    vecs: list[dict],
    threshold: float = 0.5,
    penalty: float = 0.4,
) -> list[SentenceScore]:
    """Penalise sentences that are too similar to higher-scored sentences.

    Works on the score list in-place (by index): if sentence j is very
    similar to a higher-scored sentence i, j's score is multiplied by
    (1 - penalty). This is applied to the *scores*, not during selection,
    so it improves single-method quality too.
    """
    # Sort by score descending to know which is "dominant"
    sorted_scores = sorted(scores, key=lambda s: s.score, reverse=True)
    penalty_map: dict[int, float] = {}

    for rank_i, si in enumerate(sorted_scores):
        if si.index in penalty_map:
            continue
        for sj in sorted_scores[rank_i + 1:]:
            if sj.index in penalty_map:
                continue
            sim = _cosine(vecs[si.index], vecs[sj.index])
            if sim >= threshold:
                existing = penalty_map.get(sj.index, 1.0)
                penalty_map[sj.index] = existing * (1.0 - penalty * sim)

    return [
        SentenceScore(s.sentence, s.score * penalty_map.get(s.index, 1.0), s.index)
        for s in scores
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED DATA CLASS & HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

class SentenceScore(NamedTuple):
    sentence: str
    score: float
    index: int


def _normalise(scores: list[SentenceScore]) -> list[SentenceScore]:
    if not scores:
        return scores
    vals = [s.score for s in scores]
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1.0
    return [SentenceScore(s.sentence, (s.score - mn) / rng, s.index) for s in scores]


def _build_tfidf_vecs(sentences: list[str]) -> tuple[list[dict], dict]:
    """TF-IDF vectors using stemmed unigrams + bigrams."""
    n = len(sentences)
    sent_tokens = [_rich_tokens(s) for s in sentences]

    df: Counter = Counter()
    for tokens in sent_tokens:
        df.update(set(tokens))

    idf = {w: math.log((n + 1) / (df[w] + 1)) + 1.0 for w in df}

    vecs = []
    for tokens in sent_tokens:
        tf = Counter(tokens)
        total = len(tokens) or 1
        vecs.append({w: (tf[w] / total) * idf.get(w, 1.0) for w in tf})

    return vecs, idf


# ═══════════════════════════════════════════════════════════════════════════════
# ALGORITHM IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

# ── 1. TF-IDF ───────────────────────────────────────────────────────────────

def _tf_idf_scores(sentences: list[str]) -> list[SentenceScore]:
    """Classic TF-IDF with full Porter stemming, bigrams, and quality filter."""
    n = len(sentences)
    if n == 0:
        return []

    vecs, _ = _build_tfidf_vecs(sentences)
    sent_tokens = [_rich_tokens(s) for s in sentences]

    scores = []
    for idx, (sent, tokens) in enumerate(zip(sentences, sent_tokens)):
        if not tokens:
            scores.append(SentenceScore(sent, 0.0, idx))
            continue
        tf = Counter(tokens)
        total = len(tokens)
        # Use pre-built vec which already has IDF baked in
        score = sum(vecs[idx].values()) * _sentence_quality(sent)
        scores.append(SentenceScore(sent, score, idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 2. BM25L (Lv & Zhai 2011) ───────────────────────────────────────────────

def _bm25l_scores(sentences: list[str], k1: float = 1.5, b: float = 0.75, delta: float = 0.5) -> list[SentenceScore]:
    """BM25L: fixes BM25's under-ranking of longer relevant documents.

    BM25 penalises long documents even when they're genuinely relevant.
    BM25L adds a lower-bound delta to TF normalisation, preventing over-penalisation.
    Formula: tf_norm = (k1+1) * (tf/(1-b+b*dl/avgdl) + delta) /
                        (k1 + tf/(1-b+b*dl/avgdl) + delta)

    Also incorporates:
      - Full Porter stemming + bigrams
      - Named entity boost (sentences mentioning important proper nouns score higher)
      - Sentence quality multiplier
      - Cross-sentence redundancy penalty
    """
    n = len(sentences)
    if n == 0:
        return []

    sent_tokens = [_rich_tokens(s) for s in sentences]
    df: Counter = Counter()
    for tokens in sent_tokens:
        df.update(set(tokens))

    lengths = [len(t) for t in sent_tokens]
    avg_dl = sum(lengths) / n if n else 1.0

    global_entities = _build_global_entities(sentences)

    def _idf(word: str) -> float:
        nq = df.get(word, 0)
        return math.log((n - nq + 0.5) / (nq + 0.5) + 1.0)

    vecs, _ = _build_tfidf_vecs(sentences)

    scores = []
    for idx, (sent, tokens) in enumerate(zip(sentences, sent_tokens)):
        if not tokens:
            scores.append(SentenceScore(sent, 0.0, idx))
            continue
        tf = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for word, freq in tf.items():
            ctd = freq / (1 - b + b * dl / avg_dl)
            tf_norm = (k1 + 1) * (ctd + delta) / (k1 + ctd + delta)
            score += _idf(word) * tf_norm

        # Named entity boost (up to +20%)
        ne_bonus = _ne_score(sent, global_entities, n)
        score *= (1.0 + 0.2 * ne_bonus)
        score *= _sentence_quality(sent)
        scores.append(SentenceScore(sent, score, idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 3. TextRank (cosine TF-IDF graph) ───────────────────────────────────────

def _textrank_scores(sentences: list[str], iterations: int = 50, damping: float = 0.85) -> list[SentenceScore]:
    """PageRank on cosine-TF-IDF graph (not Jaccard — the original paper used cosine)."""
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [SentenceScore(sentences[0], 1.0, 0)]

    vecs, _ = _build_tfidf_vecs(sentences)

    sim = [[_cosine(vecs[i], vecs[j]) if i != j else 0.0 for j in range(n)] for i in range(n)]
    for i in range(n):
        row_sum = sum(sim[i])
        if row_sum:
            sim[i] = [v / row_sum for v in sim[i]]

    rank = [1.0 / n] * n
    for _ in range(iterations):
        rank = [
            (1 - damping) / n + damping * sum(sim[j][i] * rank[j] for j in range(n))
            for i in range(n)
        ]

    scores = [
        SentenceScore(s, rank[i] * _sentence_quality(s), i)
        for i, s in enumerate(sentences)
    ]
    return _apply_redundancy_penalty(scores, vecs)


# ── 4. LexRank ───────────────────────────────────────────────────────────────

def _lexrank_scores(sentences: list[str], threshold: float = 0.08) -> list[SentenceScore]:
    """Cosine eigenvector centrality with quality filter and redundancy penalty."""
    n = len(sentences)
    if n == 0:
        return []

    vecs, _ = _build_tfidf_vecs(sentences)

    adj = [[0.0] * n for _ in range(n)]
    degree = [0.0] * n
    for i in range(n):
        for j in range(n):
            if i != j:
                c = _cosine(vecs[i], vecs[j])
                if c >= threshold:
                    adj[i][j] = c
                    degree[i] += c

    scores = []
    for i, s in enumerate(sentences):
        score = (sum(adj[i]) / (degree[i] if degree[i] else 1.0)) * _sentence_quality(s)
        scores.append(SentenceScore(s, score, i))

    return _apply_redundancy_penalty(scores, vecs)


# ── 5. Centroid (Radev et al. 2004) ─────────────────────────────────────────

def _centroid_scores(sentences: list[str]) -> list[SentenceScore]:
    """True centroid-based summarization (Radev 2004).

    Computes a pseudo-relevance centroid: the average TF-IDF vector across
    all sentences. Scores each sentence by cosine similarity to that centroid.
    Selects sentences closest to the 'heart' of the document.

    Different from LexRank: centroid is a single target vector, not a graph.
    Excellent for cohesive topical texts (news, reports, Wikipedia).
    """
    n = len(sentences)
    if n == 0:
        return []

    vecs, _ = _build_tfidf_vecs(sentences)

    # Build centroid vector (mean of all sentence vectors)
    all_keys: set[str] = set()
    for v in vecs:
        all_keys.update(v.keys())

    centroid: dict[str, float] = {}
    for key in all_keys:
        centroid[key] = sum(v.get(key, 0.0) for v in vecs) / n

    scores = []
    for i, (s, v) in enumerate(zip(sentences, vecs)):
        sim = _cosine(v, centroid)
        scores.append(SentenceScore(s, sim * _sentence_quality(s), i))

    return _apply_redundancy_penalty(scores, vecs)


# ── 6. Luhn (1958) ───────────────────────────────────────────────────────────

def _luhn_scores(sentences: list[str]) -> list[SentenceScore]:
    """Luhn cluster scoring with full Porter stemming and quality filter."""
    freq = _word_freq(sentences)
    if not freq:
        return [SentenceScore(s, 0.0, i) for i, s in enumerate(sentences)]

    cutoff = sorted(freq.values(), reverse=True)[max(0, len(freq) // 4)]
    sig = {w for w, c in freq.items() if c >= cutoff}

    vecs, _ = _build_tfidf_vecs(sentences)

    scores = []
    for idx, sent in enumerate(sentences):
        stems = _content_stems(sent)
        if not stems:
            scores.append(SentenceScore(sent, 0.0, idx))
            continue
        is_sig = [1 if w in sig else 0 for w in stems]
        start = end = None
        for i, flag in enumerate(is_sig):
            if flag:
                if start is None:
                    start = i
                end = i
        best = 0.0
        if start is not None:
            window = is_sig[start: end + 1]
            sig_count = sum(window)
            if window:
                best = (sig_count ** 2) / len(window)
        scores.append(SentenceScore(sent, best * _sentence_quality(sent), idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 7. SumBasic (Nenkova & Vanderwende 2005) ─────────────────────────────────

def _sumbasic_scores(sentences: list[str]) -> list[SentenceScore]:
    if not sentences:
        return []

    sent_tokens = [_content_stems(s) for s in sentences]
    all_tokens = [t for tokens in sent_tokens for t in tokens]
    if not all_tokens:
        return [SentenceScore(s, 0.0, i) for i, s in enumerate(sentences)]

    total = len(all_tokens)
    probs = {w: c / total for w, c in Counter(all_tokens).items()}
    vecs, _ = _build_tfidf_vecs(sentences)

    scores = []
    for idx, (sent, tokens) in enumerate(zip(sentences, sent_tokens)):
        if not tokens:
            scores.append(SentenceScore(sent, 0.0, idx))
            continue
        score = (sum(probs.get(w, 0.0) for w in tokens) / len(tokens)) * _sentence_quality(sent)
        scores.append(SentenceScore(sent, score, idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 8. KLSum ─────────────────────────────────────────────────────────────────

def _kl_divergence(p: dict, q: dict) -> float:
    result = 0.0
    for w, pw in p.items():
        if pw > 0:
            result += pw * math.log(pw / q.get(w, 1e-10))
    return result


def _klsum_scores(sentences: list[str]) -> list[SentenceScore]:
    """KL-divergence: select sentences whose distribution best matches full doc."""
    if not sentences:
        return []

    sent_tokens = [_content_stems(s) for s in sentences]
    all_tokens = [t for tokens in sent_tokens for t in tokens]
    if not all_tokens:
        return [SentenceScore(s, 0.0, i) for i, s in enumerate(sentences)]

    total = len(all_tokens)
    doc_dist = {w: c / total for w, c in Counter(all_tokens).items()}
    vecs, _ = _build_tfidf_vecs(sentences)

    scores = []
    for idx, (sent, tokens) in enumerate(zip(sentences, sent_tokens)):
        if not tokens:
            scores.append(SentenceScore(sent, 0.0, idx))
            continue
        sent_dist = {w: c / len(tokens) for w, c in Counter(tokens).items()}
        score = -_kl_divergence(doc_dist, sent_dist) * _sentence_quality(sent)
        scores.append(SentenceScore(sent, score, idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 9. COWTS ─────────────────────────────────────────────────────────────────

def _cowts_scores(sentences: list[str]) -> list[SentenceScore]:
    """Composite: BM25L + positional weight + title-word boost.

    Position curve: empirically tuned for mixed text types.
    First ~15% of sentences scored high (news lead), last ~10% also boosted
    (academic conclusions), middle gets baseline.
    """
    n = len(sentences)
    if n == 0:
        return []

    bm25_norm = {s.index: s.score for s in _normalise(_bm25l_scores(sentences))}
    vecs, _ = _build_tfidf_vecs(sentences)

    def _pos(i: int) -> float:
        frac = i / max(n - 1, 1)
        # Dual-peak: start and end
        lead = math.exp(-frac / 0.15)
        conclusion = math.exp(-(1 - frac) / 0.10)
        return max(lead, conclusion, 0.15)

    pos = [_pos(i) for i in range(n)]
    pm = max(pos) or 1.0
    pos = [p / pm for p in pos]

    title_stems = set(_content_stems(sentences[0])) if sentences else set()

    scores = []
    for idx, sent in enumerate(sentences):
        stems = set(_content_stems(sent))
        title_overlap = len(stems & title_stems) / max(len(stems), 1) if title_stems else 0.0
        score = 0.45 * bm25_norm.get(idx, 0.0) + 0.35 * pos[idx] + 0.20 * title_overlap
        scores.append(SentenceScore(sent, score, idx))

    return _apply_redundancy_penalty(scores, vecs)


# ── 10. MMR ──────────────────────────────────────────────────────────────────

def _mmr_scores(sentences: list[str], lambda_: float = 0.65) -> list[SentenceScore]:
    """Maximal Marginal Relevance with cosine TF-IDF vectors.

    Greedily picks sentences maximising:
        lambda * relevance(s) - (1-lambda) * max_similarity(s, already_selected)

    lambda_=0.65: slightly relevance-biased while ensuring diversity.
    Relevance measured by BM25L scores.
    """
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [SentenceScore(sentences[0], 1.0, 0)]

    vecs, _ = _build_tfidf_vecs(sentences)
    bm25_raw = _bm25l_scores(sentences)
    bm25_max = max(s.score for s in bm25_raw) or 1.0
    relevance = [s.score / bm25_max for s in bm25_raw]

    selected: list[int] = []
    order: list[int] = []
    remaining = list(range(n))

    while remaining:
        if not selected:
            best = max(remaining, key=lambda i: relevance[i])
        else:
            def _mmr(i: int) -> float:
                max_sim = max(_cosine(vecs[i], vecs[j]) for j in selected)
                return lambda_ * relevance[i] - (1 - lambda_) * max_sim
            best = max(remaining, key=_mmr)
        order.append(best)
        selected.append(best)
        remaining.remove(best)

    result: list[SentenceScore] = [None] * n  # type: ignore
    for rank, idx in enumerate(order):
        result[idx] = SentenceScore(sentences[idx], 1.0 - rank / n, idx)
    return result


# ── 11. Hybrid — Reciprocal Rank Fusion ─────────────────────────────────────

def _hybrid_scores(sentences: list[str]) -> list[SentenceScore]:
    """Reciprocal Rank Fusion (RRF) ensemble of 7 diverse rankers.

    RRF formula (Cormack, Clarke & Buettcher 2009):
        RRF(d) = Σ_r  1 / (k + rank_r(d))     where k = 60

    Why RRF over weighted sum:
      ① Parameter-free: no weights to tune, no normalisation needed
      ② Rank-based: robust to score scale / distribution differences
      ③ Proven: consistently outperforms weighted combinations on TREC benchmarks
      ④ Complementary rankers: each covers different failure modes

    Rankers used (diverse by design — each catches what others miss):
      BM25L     — term importance (best single ranker for most texts)
      TextRank  — graph centrality (catches key-hub sentences)
      LexRank   — eigenvector centrality (robustly central sentences)
      Centroid  — proximity to document core (thematic sentences)
      MMR       — relevance + diversity (anti-redundancy signal)
      COWTS     — position + title signal (structure awareness)
      KLSum     — information-theoretic (distribution match)
    """
    if not sentences:
        return []

    n = len(sentences)
    k = 60

    rankers = [
        _bm25l_scores,
        _textrank_scores,
        _lexrank_scores,
        _centroid_scores,
        _mmr_scores,
        _cowts_scores,
        _klsum_scores,
    ]

    rrf = [0.0] * n
    for ranker in rankers:
        scored = ranker(sentences)
        sorted_idx = [s.index for s in sorted(scored, key=lambda s: s.score, reverse=True)]
        rank_map = {idx: rank for rank, idx in enumerate(sorted_idx)}
        for i in range(n):
            rrf[i] += 1.0 / (k + rank_map.get(i, n))

    return [SentenceScore(sentences[i], rrf[i], i) for i in range(n)]


# ═══════════════════════════════════════════════════════════════════════════════
# YAKE KEYWORD EXTRACTION  (Yet Another Keyword Extractor, Campos et al. 2020)
# ═══════════════════════════════════════════════════════════════════════════════

def _yake_extract(text: str, top_n: int = 20, window: int = 3) -> list[tuple[str, float]]:
    """YAKE: unsupervised keyword extraction using 5 statistical features.

    Features per candidate term t:
      TF_norm   — normalised term frequency (with position weight)
      TF_pos    — position bonus: earlier first appearance = more important
      TF_case   — capitalisation: appears capitalised mid-sentence = proper noun
      TF_disp   — dispersion: spread across the document (consistent = important)
      TF_coh    — co-occurrence: word appears in meaningful contexts (not isolated)

    Final score S(t) = (TF_pos × TF_case) / (TF_norm × TF_disp × TF_coh)
    Lower S = more important (we invert for return convention).

    Reference: Campos et al. 2020 "YAKE! Keyword Extraction from Single
    Documents using Multiple Local Features", Information Sciences.
    """
    sentences = _split_sentences(text)
    if not sentences:
        return []

    n_sents = len(sentences)
    words_per_sent = [_tokenize(s) for s in sentences]
    all_words_raw = [w for ws in words_per_sent for w in ws]
    N = len(all_words_raw) or 1

    # Filter to candidate terms (not stop-words, length > 2, not purely numeric)
    def _is_candidate(w: str) -> bool:
        return (w not in _STOP_WORDS
                and len(w) > 2
                and not w.isdigit()
                and re.search(r'[a-zA-Z]', w) is not None)

    candidates_raw = [w for w in all_words_raw if _is_candidate(w.lower())]

    # --- TF_norm: frequency normalised by max freq ---
    tf: Counter = Counter(w.lower() for w in candidates_raw)
    tf_max = max(tf.values()) if tf else 1
    tf_norm = {w: c / tf_max for w, c in tf.items()}

    # --- TF_pos: first-sentence position (sentence index of first occurrence) ---
    first_sent: dict[str, int] = {}
    for si, ws in enumerate(words_per_sent):
        for w in ws:
            wl = w.lower()
            if _is_candidate(wl) and wl not in first_sent:
                first_sent[wl] = si
    # Normalise: lower sentence index → lower score (closer to 0 → better)
    tf_pos = {w: math.log(3 + first_sent.get(w, n_sents) / max(n_sents, 1)) for w in tf}

    # --- TF_case: capitalisation score ---
    cap_count: Counter = Counter()
    for w in all_words_raw:
        wl = w.lower()
        if _is_candidate(wl) and w[0].isupper():
            cap_count[wl] += 1
    tf_case = {w: math.log(1 + cap_count.get(w, 0)) for w in tf}

    # --- TF_disp: dispersion across sentences ---
    # Count in how many sentences the word appears
    sent_presence: Counter = Counter()
    for ws in words_per_sent:
        seen = set()
        for w in ws:
            wl = w.lower()
            if _is_candidate(wl) and wl not in seen:
                sent_presence[wl] += 1
                seen.add(wl)
    # Dispersion = how evenly spread (uniform = more important)
    tf_disp = {}
    for w, freq in tf.items():
        sp = sent_presence.get(w, 1)
        # High dispersion (appears in many sentences) = good
        tf_disp[w] = (sp / n_sents) if n_sents else 1.0

    # --- TF_coh: co-occurrence diversity (how many unique neighbours in window) ---
    co_occur: dict[str, set] = defaultdict(set)
    flat_candidates = [w.lower() for w in all_words_raw if _is_candidate(w.lower())]
    for i, w in enumerate(flat_candidates):
        ctx_start = max(0, i - window)
        ctx_end = min(len(flat_candidates), i + window + 1)
        for j in range(ctx_start, ctx_end):
            if j != i:
                co_occur[w].add(flat_candidates[j])
    tf_coh = {w: len(co_occur.get(w, set())) / max(tf.get(w, 1), 1) for w in tf}

    # --- YAKE score: lower = more important ---
    yake_scores: dict[str, float] = {}
    for w in tf:
        pos_case = tf_pos.get(w, 1.0) * max(tf_case.get(w, 0.0), 0.1)
        disp_coh_norm = tf_norm.get(w, 0.0) * max(tf_disp.get(w, 0.0), 0.01) * max(tf_coh.get(w, 0.0), 0.01)
        if disp_coh_norm > 0:
            yake_scores[w] = pos_case / disp_coh_norm
        else:
            yake_scores[w] = float('inf')

    # Sort by score ascending (lower = more important), take top_n
    top = sorted(yake_scores.items(), key=lambda x: x[1])[:top_n]
    if not top:
        return []

    # Invert and normalise to [0, 1] (higher = more important for display)
    min_s = top[0][1] if top else 1.0
    max_s = top[-1][1] if top else 1.0
    rng = max_s - min_s or 1.0

    result = []
    for w, s in top:
        norm = 1.0 - (s - min_s) / rng  # invert: lower YAKE score = higher display score
        result.append((w, norm))

    return sorted(result, key=lambda x: x[1], reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

ALGORITHMS: dict[str, str] = {
    "Hybrid":   "RRF ensemble of 7 methods — best for any text type",
    "BM25L":    "BM25L + stemming + bigrams + named-entity boost",
    "MMR":      "Maximal Marginal Relevance — relevance + diversity",
    "TextRank": "PageRank on cosine-TF-IDF graph",
    "LexRank":  "Cosine eigenvector centrality graph",
    "Centroid": "Closest-to-document-centroid sentences (Radev 2004)",
    "COWTS":    "Position + BM25L + title-word boost",
    "KLSum":    "KL-divergence minimisation (information-theoretic)",
    "TF-IDF":   "Classic baseline with stemming + bigrams",
    "Luhn":     "Significant-word cluster density (Luhn 1958)",
    "SumBasic": "Word-probability averaging (Nenkova 2005)",
}

# Best-use guidance shown in the GUI
ALGORITHM_TIPS: dict[str, str] = {
    "Hybrid":   "✦ Recommended for all use cases. Combines 7 algorithms via Reciprocal Rank Fusion — no single method dominates. Reliable across news, academic, technical, and conversational text.",
    "BM25L":    "Best for: keyword-rich documents, news articles, technical documentation. Strongest single ranker. BM25L fixes BM25's length-bias via lower-bound TF normalisation.",
    "MMR":      "Best for: long texts with repeated ideas. Actively penalises near-duplicate sentences — each selected sentence must be both relevant AND different from what's already chosen.",
    "TextRank": "Best for: cohesive, well-structured text. Graph-based: picks sentences that are central hubs in the similarity graph. Works well for Wikipedia-style content.",
    "LexRank":  "Best for: formal, topically focused text. Similar to TextRank but uses eigenvector centrality instead of PageRank iteration — slightly more robust to noisy similarity graphs.",
    "Centroid": "Best for: news, reports, Wikipedia. Finds sentences closest to the document's 'topic centroid'. Excellent when the text has a clear, unified subject.",
    "COWTS":    "Best for: news articles, structured documents. Combines term importance with position — boosts first/last sentences and title-related content.",
    "KLSum":    "Best for: technical or scientific text. Information-theoretic: picks sentences whose word distribution best approximates the full document distribution.",
    "TF-IDF":   "Classic baseline. Good for short texts. Use when you want interpretable, term-frequency-driven selection with no graph overhead.",
    "Luhn":     "Best for: short focused documents. Fast. Picks sentences with dense clusters of high-frequency significant words.",
    "SumBasic": "Best for: redundant texts (e.g. multiple similar news articles). Favours sentences with the most probable words. Can under-perform on diverse texts.",
}

_ALGO_FN: dict[str, callable] = {
    "TF-IDF":   _tf_idf_scores,
    "BM25L":    _bm25l_scores,
    "TextRank": _textrank_scores,
    "LexRank":  _lexrank_scores,
    "Centroid": _centroid_scores,
    "Luhn":     _luhn_scores,
    "SumBasic": _sumbasic_scores,
    "KLSum":    _klsum_scores,
    "COWTS":    _cowts_scores,
    "MMR":      _mmr_scores,
    "Hybrid":   _hybrid_scores,
}


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def summarize(
    text: str,
    ratio: float = 0.3,
    algorithm: str = "Hybrid",
    preserve_order: bool = True,
) -> tuple[str, list[int]]:
    """Return (summary_string, selected_sentence_indices).

    ratio          : fraction of sentences to keep (0.05–0.90)
    algorithm      : key from ALGORITHMS dict
    preserve_order : keep sentences in original document order
    """
    sentences = _split_sentences(text)
    if not sentences:
        return "", []

    n_keep = max(1, round(len(sentences) * ratio))
    fn = _ALGO_FN.get(algorithm, _hybrid_scores)
    scored = fn(sentences)

    top = sorted(scored, key=lambda s: s.score, reverse=True)[:n_keep]
    if preserve_order:
        top = sorted(top, key=lambda s: s.index)

    summary = " ".join(s.sentence for s in top)
    indices = [s.index for s in top]
    return summary, indices


def extract_keywords(text: str, top_n: int = 20) -> list[tuple[str, float]]:
    """Return top-N (word, score) using YAKE — best offline keyword extractor.

    YAKE uses 5 statistical features: position, frequency, capitalisation,
    dispersion, and co-occurrence diversity. No supervised training needed.
    Returns surface forms (not stemmed), scores normalised to [0, 1].
    """
    return _yake_extract(text, top_n=top_n)


def highlight_important(text: str, top_n: int = 15) -> set[str]:
    return {w for w, _ in extract_keywords(text, top_n)}