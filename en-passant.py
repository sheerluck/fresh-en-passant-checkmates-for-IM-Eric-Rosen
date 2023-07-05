"""
$ bzcat lichess_db_standard_rated_2022-07.pgn.bz2 | python en-passant.py
$ bzcat lichess_db_standard_rated_2022-08.pgn.bz2 | python en-passant.py
$ bzcat lichess_db_standard_rated_2022-09.pgn.bz2 | python en-passant.py
$ bzcat lichess_db_standard_rated_2022-10.pgn.bz2 | python en-passant.py
$ zstdcat lichess_db_standard_rated_2022-11.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2022-12.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-01.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-02.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-03.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-04.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-05.pgn.zst | python en-passant.py
$ zstdcat lichess_db_standard_rated_2023-06.pgn.zst | python en-passant.py
"""

import fileinput
from datetime import datetime
from re import sub

import parsita as p


def now():
    return f"{datetime.now():%H:%M:%S}"


def formatannotations(annotations):
    return {ant[0]: ant[1] for ant in annotations}


def formatgame(game):
    return {
        'moves': game[0],
        'outcome': game[1],
    }


def formatentry(entry):
    return {'annotations': entry[0], 'game': entry[1]}


def handleoptional(optionalmove):
    if len(optionalmove) > 0:
        return optionalmove[0]
    else:
        return None


def grammar() -> p.parsers.RepeatedParser:

    # tokens
    quote       = p.lit(r'"')
    whitespace  = p.lit(' ') | p.lit('\n')
    tag         = p.reg(r'[\u0021-\u0021\u0023-\u005A\u005E-\u007E]+')
    string      = p.reg(r'[\u0020-\u0021\u0023-\u005A\u005E-\U0010FFFF]+')

    # Annotations: [Foo "Super Awesome Information"]
    annotation  = '[' >> (tag) << ' ' & (quote >> string << quote) << ']'
    annotations = p.repsep(annotation, '\n') > formatannotations

    # Moves are more complicated
    regularmove = p.reg(r'[a-h1-8NBRQKx\+#=]+')
    longcastle  = p.reg(r'O-O-O[+#]?')           # match first
    castle      = p.reg(r'O-O[+#]?')
    nullmove    = p.lit('--')                    # Illegal move

    move        = regularmove | longcastle | castle | nullmove

    # Build up the game
    movenumber  = (p.reg(r'[0-9]+') << '.' << whitespace) > int
    turn        = movenumber & (move << whitespace)  \
        & (p.opt(move << whitespace) > handleoptional)

    draw        = p.lit('1/2-1/2')
    white       = p.lit('1-0')
    black       = p.lit('0-1')
    outcome     = draw | white | black

    game        = (p.rep(turn) & outcome) > formatgame

    # A PGN entry is annotations and the game
    entry       = ((annotations << p.rep(whitespace))
                   & (game << p.rep(whitespace))) > formatentry

    # A file is repeated entries
    return p.rep(entry)


def checkmate(s: str) -> bool:
    if s[-1] == "#":
        return True
    return False


def pawn(s: str) -> bool:
    if s[0] in 'BKNOQR':
        return False
    if "=" in s:
        return False
    return True


def nox(s: str) -> str:
    t = s.replace("+", '').replace("#", '')
    q = t.split("x")
    return q[-1]


def withoutx(s: str) -> bool:
    return "x" not in s


def withx(s: str) -> bool:
    return "x" in s


def try_elo(d: dict[str, int], line: str) -> dict:
    for elem in ["WhiteElo", "BlackElo"]:
        if elem in line:
            try:
                d[elem] = int(line.split('"')[1])
            except Exception:
                pass
    return d


def cleanup(game: str) -> str:
    no_clock = sub(r"{.+?}",       "",  game)
    no_dots  = sub(r" \d+\.\.\. ", "",  no_clock)
    no_space = sub(r"  ",          " ", no_dots)
    no_marks = sub(r"\?|\!",       "",  no_space)
    if len(no_marks) > 20:
        m = no_marks.split(".")
        no_marks = ".".join([m[0], m[-2], m[-1]])
    if no_marks.endswith("*\n"):
        no_marks = no_marks[:-2] + '1/2-1/2\n'
    return no_marks


def process(gr: p.parsers.RepeatedParser,
            counter: int,
            num: int,
            elo: dict[str, int],
            lines: list[str]) -> tuple[bool, int]:
    try:
        parsed = gr.parse("".join(lines)).or_die()
    except Exception as err:
        raise ValueError(f"{counter=}") from err
    for game in parsed:
        moves = game["game"]["moves"]
        if len(moves) >= 2:
            ann = game["annotations"]
            (n, a, b), (m, c, d) = moves[-2:]
            moves = [x for x in [a, b, c, d] if x]
            a, b  = moves[-2:]
            if all([pawn(a), pawn(b),
                    withoutx(a), withx(b),
                    checkmate(b)]):
                a, b = nox(a), nox(b)
                c1, n1 = a
                c2, n2 = b
                if c1 == c2:
                    if [n1, n2] in [['5', '6'], ['4', '3']]:
                        p = sorted(elo.values())
                        n = f"| {num:>2} | {counter:>10} "
                        s = f"| {ann['Site']} | {m:>5} "
                        e = f"| {p[1]} - {p[0]} |      "
                        print(f"{n}{s}{e} |", flush=True)
                        return True, num + 1
    return False, -1


def main() -> int:

    gr = grammar()
    lines = []
    step = "annotations"
    counter = 1
    num = 1
    elo: dict[str, int] = {}
    print(f"{counter:>10}, {now()}", flush=True)
    for line in fileinput.input():
        if len(line) > 1 and step == "annotations":
            if "Elo" in line:
                elo = try_elo(elo, line)
            if "Site" in line:
                lines.append(line)
            continue
        if len(line) == 1 and step == "annotations":
            lines.append(line)
            step = "game"
            continue
        if len(line) > 1 and step == "game":
            if min(elo.values()) > 2200:
                lines.append(cleanup(line))
            continue
        if len(line) == 1 and step == "game":
            if min(elo.values()) > 2200:
                lines.append(line)
                is_ok, n = process(gr, counter, num, elo, lines)
                if is_ok:
                    num = n
            lines = []
            step = "annotations"
            counter += 1
            elo = {}
            if counter % 1_000_000 == 0:
                print(f"{counter:>10}, {now()}", flush=True)
    return 0


if __name__ == "__main__":
    exit(main())
