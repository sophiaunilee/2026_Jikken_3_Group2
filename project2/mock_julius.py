#!/usr/bin/env python3
"""Julius(モジュールモード)のふりをする擬似サーバー。マイクなしで app.py を試せる。

起動すると 127.0.0.1:10500 で待ち受け、app.py が接続したら、
キーボードで入力した単語（draw.voca の出力文字列）を認識結果として送る。
例:  RED LARGE CIRCLE TOP_RIGHT      /      BLUE STAR LEFT      /      CLEAR
"""
import socket

HOST, PORT = "127.0.0.1", 10500


def recogout(words, cm=0.95):
    whypos = ['<WHYPO WORD="[s]" CLASSID="0" PHONE="silB" CM="1.000"/>']
    for i, w in enumerate(words, start=1):
        whypos.append(f'<WHYPO WORD="{w}" CLASSID="{i}" PHONE="x" CM="{cm:.3f}"/>')
    whypos.append('<WHYPO WORD="[/s]" CLASSID="99" PHONE="silE" CM="1.000"/>')
    body = "\n".join(whypos)
    return (f'<RECOGOUT>\n<SHYPO RANK="1" SCORE="-1000.0" GRAM="0">\n{body}\n'
            f'</SHYPO>\n</RECOGOUT>\n.\n')


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(1)
    print(f"擬似Julius待機中 {HOST}:{PORT}（app.py を起動してください）")
    while True:                      # app.py を再起動しても、また接続を受け付ける
        conn, _ = srv.accept()
        print("接続されました。単語をスペース区切りで入力 (Ctrl+Cで終了)")
        try:
            conn.sendall(b"<STARTPROC/>\n.\n")
            while True:
                line = input("> ").strip()
                if line:
                    conn.sendall(recogout(line.split()).encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError):
            print("app.py との接続が切れました。再接続を待ちます…")
            conn.close()


if __name__ == "__main__":
    main()
