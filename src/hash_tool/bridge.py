"""Hash Tool."""

import contextlib
import hashlib
import hmac as _hmac
import itertools
import json
import math
import os
import random
import secrets
import string

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QFileDialog

from src.common.config import HASH_TOOL_SETTINGS, PROJECT_ROOT
from src.nexus.utils import copy_to_clipboard

CHUNK = 8 * 1024 * 1024  # 8 MB

# All algorithms available for selection — label → hashlib name
ALL_ALGORITHMS: dict[str, str] = {
    "MD5":       "md5",
    "SHA-1":     "sha1",
    "SHA-224":   "sha224",
    "SHA-256":   "sha256",
    "SHA-384":   "sha384",
    "SHA-512":   "sha512",
    "SHA3-256":  "sha3_256",
    "SHA3-512":  "sha3_512",
    "BLAKE2b":   "blake2b",
    "BLAKE2s":   "blake2s",
    "RIPEMD-160":"ripemd160",
}

# Default selection (mirrors original behaviour)
DEFAULT_ALGORITHMS = ["MD5", "SHA-1", "SHA-256", "SHA-512"]

# Memorizable password wordlist (common short words, easy to visualise)
# EFF short wordlist 1.0 — 1296 memorable words (log2(1296)≈10.3 bits/word)
# Source: https://www.eff.org/deeplinks/2016/07/new-wordlists-random-passphrases
_WORDS = [
    "acid","acne","acre","acts","afar","afro","aged","ages","aide","aids",
    "aims","airy","ajar","akin","ally","aloe","also","alto","alum","amok",
    "amps","ankh","ante","ants","aped","apex","arch","arcs","area","aria",
    "arid","army","arts","arty","ashy","atom","atop","aunt","avid","awry",
    "axes","axle","bale","balm","banjo","bark","barn","bash","bask","bath",
    "bead","beam","bean","bear","beat","beds","beef","been","belt","bend",
    "best","bias","bike","bile","bird","bite","bits","blot","blow","blue",
    "blur","boar","bold","bolt","bone","book","boom","born","both","bout",
    "brag","bred","brew","brim","buck","buff","bulb","bull","bump","bunk",
    "burn","burp","buzz","cabs","cage","cake","calf","calm","came","cane",
    "card","care","carp","cart","cash","cast","cave","cent","chad","chat",
    "chip","chop","cite","city","clam","clan","clap","clay","clip","clog",
    "clot","club","clue","coal","coat","coil","cola","cold","come","cone",
    "cook","copy","cord","core","cork","corn","cost","cozy","cram","crew",
    "crop","crow","cube","cure","curl","daft","damp","dare","dark","dart",
    "dash","data","dawn","daze","dead","deal","dean","debt","deck","deem",
    "deer","deft","deny","desk","dew","dial","dice","dill","dime","dine",
    "dire","dirt","disk","dome","done","dorm","dose","dote","dove","down",
    "drab","drag","draw","drip","drop","drum","dual","duel","duke","dull",
    "dump","dune","dusk","dust","duty","dye","each","earl","earn","ease",
    "east","easy","edge","edit","else","emit","epic","even","ever","evil",
    "exam","expo","eyed","face","fact","fail","fake","fame","fang","fare",
    "fast","fate","fawn","faze","feat","feel","feet","fell","felt","fern",
    "fife","file","fill","film","find","fire","firm","fish","fist","five",
    "fizz","flag","flaw","flax","flea","fled","flex","flip","flit","flog",
    "flow","foam","foil","fold","fond","font","ford","fore","fork","form",
    "fort","foul","four","fowl","fray","free","from","fuel","full","fume",
    "fund","funk","fury","fuzz","gale","gall","gaze","gear","gift","glee",
    "glue","glum","gnat","gnaw","gong","good","gore","gown","grab","gram",
    "gray","grew","grid","grin","grip","grit","grow","grub","gulf","gust",
    "guys","hack","hail","hair","half","halt","hare","harm","haze","hazy",
    "head","heal","heap","heat","heed","heel","helm","hemp","herb","herd",
    "here","hewn","hick","hide","high","hike","hill","hint","hire","hoax",
    "hold","hole","home","hone","hood","hoop","hope","horn","howl","huge",
    "hump","hung","hunt","hurl","hymn","iced","icon","idea","idle","inch",
    "info","into","iris","isle","itch","item","jail","jape","jazz","jest",
    "jibe","jolt","jowl","jump","junk","just","keen","kelp","kept","kind",
    "king","knit","know","lace","lack","laid","lame","lamp","land","lane",
    "lard","lark","last","laud","lawn","lead","leaf","leak","lean","leap",
    "left","lend","lens","levy","lick","lift","like","lime","limp","link",
    "lion","lira","list","live","load","loam","loaf","loan","loft","long",
    "look","loom","loon","loot","lore","lorn","lump","lung","lurk","lush",
    "mace","mail","main","make","male","malt","mane","mare","mark","mars",
    "mask","mast","mate","mead","meal","mean","meet","melt","memo","menu",
    "mesh","mice","mild","mill","mime","mind","mine","mint","mire","mist",
    "mode","mold","mole","mood","moon","more","moss","most","moth","move",
    "much","muck","mule","murk","mutt","myth","nail","name","nape","need",
    "nest","news","next","nice","nine","node","none","noon","norm","note",
    "noun","nude","null","numb","oath","oboe","odds","omen","once","only",
    "open","opus","oral","orb","orca","oven","over","owed","owns","pace",
    "pack","page","pain","pair","pale","palm","pane","park","part","past",
    "path","pave","pawn","peak","pear","peel","peer","perm","pest","pick",
    "pier","pile","pine","pink","pity","plan","plea","plod","plot","plow",
    "ploy","plug","plum","plus","poem","poet","poke","pole","poll","pond",
    "pore","port","pose","post","pour","pray","prep","prey","prim","prod",
    "prop","pull","pulp","pump","pure","push","rack","rage","raid","rail",
    "rain","rake","ramp","rang","rank","rare","rash","rasp","rave","read",
    "real","reap","rear","rein","rely","rend","rent","rest","rice","rich",
    "rick","ride","rift","ring","riot","ripe","rise","risk","roam","roar",
    "robe","rode","role","roll","roof","room","root","rope","rose","rout",
    "rove","rube","ruby","ruin","rule","rung","runt","ruse","rush","rust",
    "rut","sage","said","sail","sale","salt","same","sand","sane","sang",
    "sank","sash","save","scam","scan","scar","seam","seat","seed","seek",
    "seem","seep","sell","send","serb","sewn","shed","shin","ship","shoe",
    "shop","shot","show","shun","shut","silk","silt","sing","sink","site",
    "size","ski","skim","skin","skip","slab","slam","slap","slim","slip",
    "slot","slow","slug","smog","snap","snip","snow","soak","soar","sock",
    "soft","soil","sole","some","song","soot","sort","soul","span","spar",
    "spin","spit","spot","spun","spur","stab","stag","star","stem","step",
    "stew","stir","stop","stub","stud","stun","such","suit","sump","sunk",
    "sure","surf","swam","swap","swat","sway","swim","swum","tact","tail",
    "tale","tall","tame","tang","tank","tape","tare","taut","teal","tell",
    "temp","tent","term","text","than","that","thaw","them","then","they",
    "thin","thud","tick","tide","tier","tile","till","time","tiny","tire",
    "toll","tomb","tone","took","tool","torn","tote","tour","town","tram",
    "trap","tray","tree","trek","trim","trio","trip","trod","true","tube",
    "tuft","tune","turf","turn","tusk","tutu","type","used","user","vain",
    "vale","vamp","vane","vary","vast","veil","vein","vent","very","vest",
    "veto","vice","view","vine","visa","void","volt","vote","wade","wage",
    "wake","walk","wall","wand","ward","warm","wart","wary","wave","weal",
    "wean","weld","well","wend","went","were","west","what","when","whim",
    "whip","whiz","whom","wick","wile","will","wilt","wimp","wind","wine",
    "wing","wink","wire","wise","wish","wisp","wolf","womb","word","wore",
    "work","worm","wren","writ","yawn","year","yell","yore","your","zero",
    "zest","zinc","zone","zoom",
]

_LEET: dict[str, str] = {
    "a": "4", "e": "3", "i": "1", "o": "0",
    "s": "$", "t": "7", "g": "9", "l": "1",
}

_SEPARATORS = ["_", "-", ".", "!", "@", "#"]


def _leet(word: str) -> str:
    """Apply leet-speak substitutions to ~half the eligible characters."""
    result: list[str] = []
    for ch in word:
        low = ch.lower()
        sub: str = _LEET.get(low, ch)
        result.append(sub if (low in _LEET and random.random() < 0.55) else ch)
    if not result:
        return word
    joined = "".join(result)
    return joined.capitalize()


def _capitalise_random(word: str) -> str:
    return word.capitalize()


_AMBIGUOUS = set("0O1lI|`'\";:.,")

def _make_random_pw(length: int, use_upper: bool, use_lower: bool,
                    use_digits: bool, use_symbols: bool,
                    custom_chars: str, exclude_ambiguous: bool = False,
                    extra_chars: str = "", exclude_chars: str = "") -> str:
    excl = set(exclude_chars)
    if exclude_ambiguous:
        excl |= _AMBIGUOUS

    def _clean(s: str) -> str:
        return "".join(c for c in s if c not in excl)

    sym_pool = "!@#$%^&*()-_=+[]{}|;:,.<>?"

    pool = custom_chars or ""
    if not custom_chars:
        if use_lower:
            pool += string.ascii_lowercase
        if use_upper:
            pool += string.ascii_uppercase
        if use_digits:
            pool += string.digits
        if use_symbols:
            pool += sym_pool
        pool += extra_chars
    pool = _clean(pool)
    # deduplicate while preserving order
    seen: set[str] = set()
    pool = "".join(c for c in pool if not (c in seen or seen.add(c)))  # type: ignore[func-returns-value]

    if not pool:
        pool = string.ascii_letters + string.digits

    # Guarantee at least one char from each requested class
    required: list[str] = []
    if not custom_chars:
        lower_pool = _clean(string.ascii_lowercase)
        upper_pool = _clean(string.ascii_uppercase)
        digit_pool = _clean(string.digits)
        sym_clean = _clean(sym_pool + extra_chars)
        if use_lower and lower_pool:
            required.append(secrets.choice(lower_pool))
        if use_upper and upper_pool:
            required.append(secrets.choice(upper_pool))
        if use_digits and digit_pool:
            required.append(secrets.choice(digit_pool))
        if use_symbols and sym_clean:
            required.append(secrets.choice(sym_clean))

    need = max(0, length - len(required))
    rest: list[str] = [secrets.choice(pool) for _ in range(need)]
    combined: list[str] = list(required) + rest
    random.shuffle(combined)
    return "".join(itertools.islice(combined, length))


_BUNDLED_CACHE: list[str] = []


def _load_bundled() -> list[str]:
    """Load and cache the bundled wordlist (reads file once, then reuses)."""
    if _BUNDLED_CACHE:
        return _BUNDLED_CACHE
    path = os.path.join(PROJECT_ROOT, "assets", "codenames.txt")
    seen: set[str] = set()
    with contextlib.suppress(OSError), open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            w = line.strip().lower()
            if w and w not in seen and w.isalpha() and 2 <= len(w) <= 20:
                seen.add(w)
                _BUNDLED_CACHE.append(w)
    return _BUNDLED_CACHE


def _build_wordlist(custom_words: list[str], use_bundled: bool = False) -> list[str]:
    """Merge built-in words with custom words (and optionally bundled file)."""
    base = _load_bundled() if use_bundled else _WORDS
    merged = list(base)
    seen: set[str] = set(merged)
    for w in custom_words:
        w = w.strip().lower()
        if w and w not in seen:
            seen.add(w)
            merged.append(w)
    return merged


def _pick_words(wordlist: list[str], count: int) -> list[str]:
    """Pick *count* distinct words using random.sample (O(count), not O(n))."""
    n = len(wordlist)
    if n >= count:
        return random.sample(wordlist, count)
    # wordlist smaller than requested — repeat with extras
    chosen = list(wordlist)
    while len(chosen) < count:
        chosen.append(secrets.choice(wordlist))
    return chosen


def _make_leet_pw(word_count: int, use_digits: bool,
                  use_symbols: bool, custom_words: list[str], use_bundled: bool = False) -> str:
    wordlist = _build_wordlist(custom_words, use_bundled)
    chosen = _pick_words(wordlist, word_count)
    sep = secrets.choice(_SEPARATORS)
    parts = [_leet(w) for w in chosen]
    pw = sep.join(parts)
    if use_digits:
        pw += str(secrets.randbelow(100))
    if use_symbols:
        pw += secrets.choice("!@#$%^&*")
    return pw


def _make_passphrase(word_count: int, separator: str,
                     custom_words: list[str], use_bundled: bool = False) -> str:
    wordlist = _build_wordlist(custom_words, use_bundled)
    words = [w.capitalize() for w in _pick_words(wordlist, word_count)]
    return separator.join(words)


def _make_pattern_pw(pattern: str, custom_words: list[str], use_bundled: bool = False) -> str:
    """
    Pattern chars:
      u = uppercase letter
      l = lowercase letter
      d = digit
      s = symbol
      w = random word from list (capitalised)
      * = any random printable (no space)
    Everything else is kept verbatim.
    """
    wordlist = _build_wordlist(custom_words, use_bundled)
    word_count = pattern.count("w") or 1
    word_cycle = itertools.cycle(_pick_words(wordlist, word_count))

    result: list[str] = []
    for ch in pattern:
        if ch == "u":
            result.append(secrets.choice(string.ascii_uppercase))
        elif ch == "l":
            result.append(secrets.choice(string.ascii_lowercase))
        elif ch == "d":
            result.append(secrets.choice(string.digits))
        elif ch == "s":
            result.append(secrets.choice("!@#$%^&*()-_=+"))
        elif ch == "w":
            result.append(next(word_cycle).capitalize())
        elif ch == "*":
            result.append(secrets.choice(string.ascii_letters + string.digits + "!@#$"))
        else:
            result.append(ch)
    return "".join(result)


# ── Background worker ─────────────────────────────────────────────────────────

class _FileHashWorker(QThread):
    progress = pyqtSignal(int)
    result   = pyqtSignal(str)   # JSON

    def __init__(self, path: str, algorithms: list[str], parent=None):
        super().__init__(parent)
        self._path = path
        self._algorithms = algorithms

    def run(self):
        try:
            size = os.path.getsize(self._path)
            algos = {}
            for label in self._algorithms:
                name = ALL_ALGORITHMS.get(label)
                if name:
                    with contextlib.suppress(ValueError):
                        algos[label] = hashlib.new(name)
            done = 0
            with open(self._path, "rb") as f:
                while chunk := f.read(CHUNK):
                    for h in algos.values():
                        h.update(chunk)
                    done += len(chunk)
                    if size:
                        self.progress.emit(int(done * 100 / size))
            self.result.emit(json.dumps({k: v.hexdigest() for k, v in algos.items()}))
        except Exception as exc:
            self.result.emit(json.dumps({"error": str(exc)}))


# ── Bridge ────────────────────────────────────────────────────────────────────

class HashToolBridge(QObject):
    """Singleton object registered as ``pyBridge`` in the QWebChannel."""

    # Pushed to JS
    hash_progress = pyqtSignal(int)   # 0-100
    hash_complete = pyqtSignal(str)   # JSON {label: hexdigest, ...}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _FileHashWorker | None = None

    # ── Algorithm listing ──────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def get_algorithms(self) -> str:
        """Return JSON list of all supported algorithm labels."""
        return json.dumps(list(ALL_ALGORITHMS.keys()))

    # ── File hashing ──────────────────────────────────────────────────────────

    @pyqtSlot(str, str)
    def hash_file(self, path: str, algorithms_json: str = "") -> None:
        """Start async file hashing; result arrives via *hash_complete* signal."""
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            self.hash_complete.emit(json.dumps({"error": f"File not found: {path}"}))
            return

        try:
            algorithms = json.loads(algorithms_json) if algorithms_json else DEFAULT_ALGORITHMS
        except (json.JSONDecodeError, ValueError):
            algorithms = DEFAULT_ALGORITHMS

        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(500)

        self._worker = _FileHashWorker(path, algorithms, self)
        self._worker.progress.connect(self.hash_progress)
        self._worker.result.connect(self.hash_complete)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    # ── Text hashing ──────────────────────────────────────────────────────────

    @pyqtSlot(str, str, str, result=str)
    def hash_text(self, text: str, hmac_key: str, algorithms_json: str = "") -> str:
        """Return JSON with hashes for *text* using the selected algorithms."""
        try:
            algorithms = json.loads(algorithms_json) if algorithms_json else DEFAULT_ALGORITHMS
        except (json.JSONDecodeError, ValueError):
            algorithms = DEFAULT_ALGORITHMS

        data = text.encode()
        key_bytes: bytes | None = hmac_key.encode() if hmac_key else None
        out: dict[str, str] = {}
        for label in algorithms:
            name = ALL_ALGORITHMS.get(label)
            if not name:
                continue
            try:
                if key_bytes is not None:
                    h = _hmac.new(key_bytes, data, name).hexdigest()
                else:
                    h = hashlib.new(name, data).hexdigest()
                out[label] = h
            except Exception as exc:
                out[label] = f"error: {exc}"
        return json.dumps(out)

    # ── Password generation ───────────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def generate_password(self, options_json: str) -> str:
        """
        Generate a password according to *options_json* and return JSON:
          {"password": "...", "entropy_bits": float}

        options keys:
          mode: "random" | "leet" | "passphrase" | "pattern"

          -- random --
          length:       int   (default 20)
          use_upper:    bool
          use_lower:    bool
          use_digits:   bool
          use_symbols:  bool
          custom_chars: str   (overrides charsets if non-empty)

          -- leet --
          word_count:    int  (default 3)
          use_digits:    bool
          use_symbols:   bool
          custom_words:  list[str]

          -- passphrase --
          word_count:   int   (default 4)
          separator:    str   (default "-")
          custom_words: list[str]

          -- pattern --
          pattern:      str   (default "wdws")
          custom_words: list[str]
        """
        try:
            opts = json.loads(options_json)
        except Exception:
            opts = {}

        mode = opts.get("mode", "random")
        try:
            use_bundled = bool(opts.get("use_bundled", False))
            entropy = 0.0

            if mode == "random":
                # Build pool the same way _make_random_pw does, measure its size
                _ambiguous = "0O1lI|`'\"" if bool(opts.get("exclude_ambiguous", False)) else ""
                def _rclean(s: str) -> str:
                    excl = str(opts.get("exclude_chars", "")) + _ambiguous
                    return "".join(c for c in s if c not in excl)
                _sym = "!@#$%^&*()-_=+[]{}|;:,.<>?"
                cc = str(opts.get("custom_chars", ""))
                if cc:
                    pool_str = cc
                else:
                    pool_str = ""
                    if bool(opts.get("use_lower", True)):
                        pool_str += _rclean(string.ascii_lowercase)
                    if bool(opts.get("use_upper", True)):
                        pool_str += _rclean(string.ascii_uppercase)
                    if bool(opts.get("use_digits", True)):
                        pool_str += _rclean(string.digits)
                    if bool(opts.get("use_symbols", True)):
                        pool_str += _rclean(_sym + str(opts.get("extra_chars", "")))
                seen_p: set[str] = set()
                pool_str = "".join(c for c in pool_str if not (c in seen_p or seen_p.add(c)))  # type: ignore[func-returns-value]
                pool_size = len(pool_str) or 62
                pw = _make_random_pw(
                    length=int(opts.get("length", 20)),
                    use_upper=bool(opts.get("use_upper", True)),
                    use_lower=bool(opts.get("use_lower", True)),
                    use_digits=bool(opts.get("use_digits", True)),
                    use_symbols=bool(opts.get("use_symbols", True)),
                    custom_chars=cc,
                    exclude_ambiguous=bool(opts.get("exclude_ambiguous", False)),
                    extra_chars=str(opts.get("extra_chars", "")),
                    exclude_chars=str(opts.get("exclude_chars", "")),
                )
                entropy = math.log2(pool_size) * len(pw)

            elif mode == "leet":
                cw: list[str] = [str(w) for w in opts.get("custom_words", [])]
                wc = int(opts.get("word_count", 3))
                wordlist = _build_wordlist(cw, use_bundled)
                pw = _make_leet_pw(word_count=wc, use_digits=bool(opts.get("use_digits", True)),
                                   use_symbols=bool(opts.get("use_symbols", True)),
                                   custom_words=cw, use_bundled=use_bundled)
                # entropy = word choices + leet substitution (each leet char ~1 extra bit) + digit + symbol
                leet_bits = sum(1 for c in pw if c in _LEET.values())
                entropy = math.log2(len(wordlist)) * wc + leet_bits + (6.6 if bool(opts.get("use_digits", True)) else 0) + (3.0 if bool(opts.get("use_symbols", True)) else 0)

            elif mode == "passphrase":
                cw2: list[str] = [str(w) for w in opts.get("custom_words", [])]
                wc2 = int(opts.get("word_count", 4))
                wordlist2 = _build_wordlist(cw2, use_bundled)
                pw = _make_passphrase(word_count=wc2, separator=str(opts.get("separator", "-")),
                                      custom_words=cw2, use_bundled=use_bundled)
                # each word is one independent pick from the wordlist
                entropy = math.log2(len(wordlist2)) * wc2

            elif mode == "pattern":
                cw3: list[str] = [str(w) for w in opts.get("custom_words", [])]
                pattern_str = str(opts.get("pattern", "wdws"))
                wordlist3 = _build_wordlist(cw3, use_bundled)
                pw = _make_pattern_pw(pattern=pattern_str, custom_words=cw3, use_bundled=use_bundled)
                # sum entropy per pattern token
                for ch in pattern_str:
                    if ch == "u" or ch == "l":
                        entropy = entropy + math.log2(26)
                    elif ch == "d":
                        entropy = entropy + math.log2(10)
                    elif ch == "s":
                        entropy = entropy + math.log2(14)
                    elif ch == "w":
                        entropy = entropy + math.log2(len(wordlist3))
                    elif ch == "*":
                        entropy = entropy + math.log2(70)
                    # literal chars contribute 0 (attacker knows the pattern)
            else:
                pw = _make_random_pw(20, True, True, True, True, "")
                entropy = math.log2(62) * 20

            # Pad to min_length if requested (leet/passphrase/pattern modes)
            min_length = int(opts.get("min_length", 0))
            if min_length > len(pw):
                pad_pool = string.ascii_letters + string.digits + "!@#$"
                pad: list[str] = [secrets.choice(pad_pool) for _ in range(min_length - len(pw))]
                pw = pw + "".join(pad)
                entropy = entropy + math.log2(len(pad_pool)) * (min_length - len(pw) + len(pad))

            # Truncate to max_length if set
            max_length = int(opts.get("max_length", 0))
            if max_length > 0 and len(pw) > max_length:
                pw = "".join(itertools.islice(iter(pw), max_length))
                # re-estimate after truncation — scale linearly
                entropy = entropy * (max_length / max(len(pw), 1))

            entropy_str = f"{entropy:.1f}"
            return json.dumps({"password": pw, "entropy_bits": entropy_str})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    # ── File dialog ───────────────────────────────────────────────────────────

    @pyqtSlot(result=str)
    def browse_file(self) -> str:
        """Open a native file-picker dialog and return the chosen path (or "")."""
        path, _ = QFileDialog.getOpenFileName(None, "Select File")
        return path or ""

    # ── File info ─────────────────────────────────────────────────────────────

    @pyqtSlot(str, result=str)
    def file_info(self, path: str) -> str:
        """Return JSON with name, size_bytes, size_str for *path*."""
        path = path.strip().strip('"')
        if not os.path.isfile(path):
            return json.dumps({})
        size = os.path.getsize(path)
        if size < 1024:
            size_str = f"{size} B"
        elif size < 1024 ** 2:
            size_str = f"{size/1024:.1f} KB"
        elif size < 1024 ** 3:
            size_str = f"{size/1024**2:.2f} MB"
        else:
            size_str = f"{size/1024**3:.2f} GB"
        return json.dumps({
            "name":       os.path.basename(path),
            "size_bytes": size,
            "size_str":   size_str,
            "path":       path,
        })

    # ── Bundled wordlist info ──────────────────────────────────────────────────

    @pyqtSlot(result=int)
    def bundled_wordlist_count(self) -> int:
        """Return the number of valid words in the bundled codenames.txt."""
        return len(_load_bundled())

    # ── Settings persistence ───────────────────────────────────────────────────

    @pyqtSlot(str)
    def save_settings(self, json_str: str) -> None:
        """Persist UI settings to data/nexus_hash_tool.json."""
        with contextlib.suppress(Exception), open(HASH_TOOL_SETTINGS, "w", encoding="utf-8") as fh:
            fh.write(json_str)

    @pyqtSlot(result=str)
    def load_settings(self) -> str:
        """Load UI settings from data/nexus_hash_tool.json. Returns '{}' if missing."""
        with contextlib.suppress(Exception), open(HASH_TOOL_SETTINGS, encoding="utf-8") as fh:
            return fh.read()
        return "{}"

    # ── Clipboard ─────────────────────────────────────────────────────────────

    @pyqtSlot(str)
    def copy_to_clipboard(self, text: str) -> None:
        """Copy *text* to the system clipboard."""
        copy_to_clipboard(text)
