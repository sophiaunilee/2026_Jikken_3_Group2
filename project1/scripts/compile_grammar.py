#!/usr/bin/env python3

import os
from collections import deque

DIGRAPHS = {
    "きゃ": "ky a", "きゅ": "ky u", "きょ": "ky o",
    "しゃ": "sh a", "しゅ": "sh u", "しぇ": "sh e", "しょ": "sh o",
    "ちゃ": "ch a", "ちゅ": "ch u", "ちぇ": "ch e", "ちょ": "ch o",
    "にゃ": "ny a", "にゅ": "ny u", "にょ": "ny o",
    "ひゃ": "hy a", "ひゅ": "hy u", "ひょ": "hy o",
    "みゃ": "my a", "みゅ": "my u", "みょ": "my o",
    "りゃ": "ry a", "りゅ": "ry u", "りょ": "ry o",
    "ぎゃ": "gy a", "ぎゅ": "gy u", "ぎょ": "gy o",
    "じゃ": "j a",  "じゅ": "j u",  "じぇ": "j e",  "じょ": "j o",
    "ぢゃ": "j a",  "ぢゅ": "j u",  "ぢぇ": "j e",  "ぢょ": "j o",
    "びゃ": "by a", "びゅ": "by u", "びょ": "by o",
    "ぴゃ": "py a", "ぴゅ": "py u", "ぴょ": "py o",
    "ふぁ": "f a",  "ふぃ": "f i",  "ふぇ": "f e",  "ふぉ": "f o",
    "てぃ": "t i",  "でぃ": "d i",  "うぃ": "w i",  "うぇ": "w e",
}

MONOGRAPHS = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o",
    "か": "k a", "き": "k i", "く": "k u", "け": "k e", "こ": "k o",
    "さ": "s a", "し": "sh i", "す": "s u", "せ": "s e", "そ": "s o",
    "た": "t a", "ち": "ch i", "つ": "ts u", "て": "t e", "と": "t o",
    "な": "n a", "に": "n i", "ぬ": "n u", "ね": "n e", "の": "n o",
    "は": "h a", "ひ": "h i", "ふ": "f u", "へ": "h e", "ほ": "h o",
    "ま": "m a", "み": "m i", "む": "m u", "め": "m e", "も": "m o",
    "や": "y a", "ゆ": "y u", "よ": "y o",
    "ら": "r a", "り": "r i", "る": "r u", "れ": "r e", "ろ": "r o",
    "わ": "w a", "を": "o", "ん": "N", "っ": "q",
    "が": "g a", "ぎ": "g i", "ぐ": "g u", "げ": "g e", "ご": "g o",
    "ざ": "z a", "じ": "j i", "ず": "z u", "ぜ": "z e", "ぞ": "z o",
    "だ": "d a", "ぢ": "j i", "づ": "z u", "で": "d e", "ど": "d o",
    "ば": "b a", "び": "b i", "ぶ": "b u", "べ": "b e", "ぼ": "b o",
    "ぱ": "p a", "ぴ": "p i", "ぷ": "p u", "ぺ": "p e", "ぽ": "p o",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o",
}


def yomi_to_phonemes(yomi: str) -> str:
    """ひらがな読みを Julius 標準の音素表記（例: m a N n a k a）に変換"""
    if yomi in ("silB", "silE", "sp"):
        return yomi

    tokens = []
    i = 0
    while i < len(yomi):
        if i + 1 < len(yomi) and yomi[i:i + 2] in DIGRAPHS:
            tokens.append(DIGRAPHS[yomi[i:i + 2]])
            i += 2
        elif yomi[i] == "ー":
            if tokens and tokens[-1][-1] in "aiueo":
                tokens[-1] = tokens[-1] + ":"
            i += 1
        elif yomi[i] in MONOGRAPHS:
            tokens.append(MONOGRAPHS[yomi[i]])
            i += 1
        else:
            tokens.append(yomi[i])
            i += 1

    flat = " ".join(tokens).split()
    merged = []
    for idx, p in enumerate(flat):
        is_last = (idx == len(flat) - 1)
        if merged and merged[-1].endswith("o") and p in ("u", "o"):
            merged[-1] = merged[-1] + ":"
        elif merged and merged[-1].endswith("u") and p == "u":
            merged[-1] = merged[-1] + ":"
        elif merged and merged[-1].endswith("a") and p == "a":
            merged[-1] = merged[-1] + ":"
        elif merged and merged[-1].endswith("i") and p == "i" and not is_last:
            merged[-1] = merged[-1] + ":"
        elif merged and merged[-1].endswith("e") and p == "e":
            merged[-1] = merged[-1] + ":"
        else:
            merged.append(p)
    return " ".join(merged)


def compile_julius_grammar(grammar_dir: str, prefix: str = "test"):
    yomi_path = os.path.join(grammar_dir, f"{prefix}.yomi")
    gram_path = os.path.join(grammar_dir, f"{prefix}.grammar")
    voca_path = os.path.join(grammar_dir, f"{prefix}.voca")
    term_path = os.path.join(grammar_dir, f"{prefix}.term")
    dict_path = os.path.join(grammar_dir, f"{prefix}.dict")
    dfa_path = os.path.join(grammar_dir, f"{prefix}.dfa")

    categories = []  
    current_cat = None

    with open(yomi_path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            if raw.startswith("%"):
                cat_name = raw[1:].strip()
                current_cat = (cat_name, [])
                categories.append(current_cat)
            elif current_cat is not None:
                parts = raw.split()
                if len(parts) >= 2:
                    word, yomi = parts[0], parts[1]
                    phonemes = yomi_to_phonemes(yomi)
                    current_cat[1].append((word, phonemes))

    term_id_map = {}
    with open(voca_path, "w", encoding="utf-8") as fvoca, \
         open(term_path, "w", encoding="utf-8") as fterm, \
         open(dict_path, "w", encoding="utf-8") as fdict:
        for tid, (cat_name, words) in enumerate(categories):
            term_id_map[cat_name] = tid
            fvoca.write(f"% {cat_name}\n")
            fterm.write(f"{tid}\t{cat_name}\n")
            for word, phonemes in words:
                fvoca.write(f"{word}\t{phonemes}\n")
                fdict.write(f"{tid}\t[{word}]\t{phonemes}\n")

    rules = {}
    with open(gram_path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.split("#")[0].strip()
            if not raw or ":" not in raw:
                continue
            lhs, rhs = raw.split(":", 1)
            lhs = lhs.strip()
            rhs_syms = rhs.strip().split()
            rules.setdefault(lhs, []).append(rhs_syms)

    def expand(sym):
        if sym in term_id_map:
            return [[term_id_map[sym]]]
        results = []
        for rhs in rules.get(sym, []):
            sub_lists = [[]]
            for s in rhs:
                expanded_s = expand(s)
                sub_lists = [prev + item for prev in sub_lists for item in expanded_s]
            results.extend(sub_lists)
        return results

    sentences = expand("S")

    trie_transitions = {0: {}}
    accepting_states = set()
    next_state_id = 1

    for seq in sentences:
        rev_seq = list(reversed(seq))
        state = 0
        for tid in rev_seq:
            if tid not in trie_transitions[state]:
                trie_transitions[state][tid] = next_state_id
                trie_transitions[next_state_id] = {}
                next_state_id += 1
            state = trie_transitions[state][tid]
        accepting_states.add(state)

    state_map = {}
    changed = True
    while changed:
        changed = False
        signatures = {}
        new_map = {}
        for s in range(next_state_id):
            s_rep = state_map.get(s, s)
            if s != s_rep:
                continue
            trans_sig = tuple(sorted((tid, state_map.get(dst, dst)) for tid, dst in trie_transitions[s].items()))
            sig = (s in accepting_states, trans_sig)
            if sig in signatures:
                new_map[s] = signatures[sig]
                changed = True
            else:
                signatures[sig] = s
                new_map[s] = s
        for s in range(next_state_id):
            rep = state_map.get(s, s)
            state_map[s] = new_map.get(rep, rep)

    remap = {state_map.get(0, 0): 0}
    queue = deque([state_map.get(0, 0)])
    ordered_reps = []
    while queue:
        curr = queue.popleft()
        ordered_reps.append(curr)
        for tid, dst in sorted(trie_transitions[curr].items()):
            dst_rep = state_map.get(dst, dst)
            if dst_rep not in remap:
                remap[dst_rep] = len(remap)
                queue.append(dst_rep)

    with open(dfa_path, "w", encoding="utf-8") as fdfa:
        for rep in ordered_reps:
            sid = remap[rep]
            trans = trie_transitions[rep]
            if trans:
                for tid, dst in sorted(trans.items()):
                    dst_id = remap[state_map.get(dst, dst)]
                    fdfa.write(f"{sid} {tid} {dst_id} 0 0\n")
            if rep in accepting_states:
                fdfa.write(f"{sid} -1 -1 1 0\n")

    print(f"文法コンパイル完了: {len(categories)} カテゴリ, {len(sentences)} 文パターン, {len(ordered_reps)} DFA状態")


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compile_julius_grammar(os.path.join(base_dir, "asr", "grammar"), "test")
