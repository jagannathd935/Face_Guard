"""Download dlib 68-point shape predictor into models/. Run: py -3 scripts/download_shape_predictor.py"""
import bz2
import os
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_DIR = os.path.join(ROOT, "models")
URL = "http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2"
BZ2_PATH = os.path.join(OUT_DIR, "shape_predictor_68_face_landmarks.dat.bz2")
DAT_PATH = os.path.join(OUT_DIR, "shape_predictor_68_face_landmarks.dat")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.isfile(DAT_PATH):
        print("Already present:", DAT_PATH)
        return
    print("Downloading", URL)
    urllib.request.urlretrieve(URL, BZ2_PATH)
    print("Extracting…")
    with bz2.open(BZ2_PATH, "rb") as f_in, open(DAT_PATH, "wb") as f_out:
        f_out.write(f_in.read())
    os.remove(BZ2_PATH)
    print("Done:", DAT_PATH)


if __name__ == "__main__":
    main()
