import os
import urllib.request

libs = {
    "react.min.js": "https://unpkg.com/react@18/umd/react.production.min.js",
    "react-dom.min.js": "https://unpkg.com/react-dom@18/umd/react-dom.production.min.js",
    "babel.min.js": "https://unpkg.com/@babel/standalone/babel.min.js",
    "framer-motion.js": "https://unpkg.com/framer-motion@10.16.4/dist/framer-motion.js",
    "tailwind.min.js": "https://cdn.tailwindcss.com",
}

print("Initiating tactical dependency localization...")

for filename, url in libs.items():
    if not os.path.exists(filename):
        print(f"Downloading {filename}...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with (
                urllib.request.urlopen(req) as response,
                open(filename, "wb") as out_file,
            ):
                out_file.write(response.read())
            print(f"Successfully localized {filename}")
        except Exception as e:
            print(f"Failed to download {filename}: {e}")
    else:
        print(f"{filename} already present.")

print("Localization complete.")
