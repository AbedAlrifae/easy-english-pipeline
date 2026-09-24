#!/usr/bin/env python3
"""Vocabulary and sentence-length gate for Easy English Stories scripts."""
import argparse, re, sys
from wordfreq import zipf_frequency

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")

def split_sentences(text):
    text = re.sub(r'\s+', ' ', text).strip()
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]

def load_text(path):
    raw = open(path, encoding='utf-8').read()
    raw = re.sub(r'^#.*$', '', raw, flags=re.M)      # strip any headings
    raw = raw.replace('"', '').replace('“', '').replace('”', '')
    return raw

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('script')
    ap.add_argument('--min-zipf', type=float, required=True)
    ap.add_argument('--max-words', type=int, required=True)
    ap.add_argument('--names', default='')
    ap.add_argument('--max-oov', type=int, default=4)
    a = ap.parse_args()

    names = set()
    for n in a.names.split(','):
        n = n.strip().lower()
        if n:
            names.add(n)
            names.add(n.replace("'s", ''))

    text = load_text(a.script)
    sents = split_sentences(text)

    total_words = 0
    long_sents = []
    oov = {}
    for i, s in enumerate(sents, 1):
        ws = WORD_RE.findall(s)
        total_words += len(ws)
        if len(ws) > a.max_words:
            long_sents.append((i, len(ws), s))
        for w in ws:
            lw = w.lower()
            if lw in names or lw.replace("'s", '') in names:
                continue
            if zipf_frequency(lw, 'en') < a.min_zipf:
                oov.setdefault(lw, []).append(i)

    print(f"sentences : {len(sents)}")
    print(f"words     : {total_words}")
    print(f"avg/sent  : {total_words/max(1,len(sents)):.1f}")
    print()

    if long_sents:
        print(f"--- {len(long_sents)} SENTENCE(S) OVER {a.max_words} WORDS ---")
        for i, n, s in long_sents:
            print(f"  [{i}] ({n}w) {s}")
        print()

    print(f"--- {len(oov)} OUT-OF-LEVEL WORD(S) (zipf < {a.min_zipf}) ---")
    for w in sorted(oov, key=lambda x: zipf_frequency(x, 'en')):
        print(f"  {w:<20} zipf={zipf_frequency(w,'en'):.2f}  sentences {oov[w]}")
    print()

    ok = True
    if long_sents:
        print(f"FAIL: {len(long_sents)} sentence(s) exceed {a.max_words} words")
        ok = False
    if len(oov) > a.max_oov:
        print(f"FAIL: {len(oov)} out-of-level words, limit is {a.max_oov}")
        ok = False
    if ok:
        print(f"PASS: {len(oov)} out-of-level word(s), all sentences within {a.max_words} words")
    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()
