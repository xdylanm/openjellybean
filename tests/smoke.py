"""Mixed-circuit smoke test: every device family together in one transient run.

CE amp -> TL07X inverting amp -> 2N7000 switch with zener clamp, plus a PNP current
source, a BS250 high side, an LM358 on a single supply, and N and P JFET followers.
"""
CIRCUIT = """VCC vcc 0 15
VEE vee 0 -15
VIN in 0 SIN(0 10m 1k)
C1 in b 10u
R1 vcc b 100k
R2 b 0 12k
Q1 c b e BC547B_OJ
RC vcc c 10k
RE e 0 1k
CE e 0 100u
C2 c x 10u
Rx x 0 100k
Ri x inv 10k
Rf inv oa 47k
XU1 0 inv vcc vee oa TL07X_OJ
Rg oa g 1k
M1 d g 0 2N7000_OJ
RL vcc d 1k
Xz 0 d BZX79C12_OJ
Q2 pc pb vcc BC557B_OJ
Rpb pb 0 220k
Rpc pc 0 1k
D1 oa sk 1N5819_OJ
Rs sk 0 10k
M2 hd hg vcc BS250_OJ
Rhg hg d 10k
Rhd hd 0 1k
XU2 sk n2 vcc 0 o2 LM358_OJ
R5 o2 n2 10k
D2 n2 0 1N4148_OJ
J1 vcc oa jn 2N5457_OJ
Rjn jn vee 10k
J2 vee oa jp 2N5460_OJ
Rjp vcc jp 10k"""


def run_smoke(sim):
    """Return a list of (description, passed, detail) for the mixed circuit."""
    t, oa, d, jn, jp = sim.run(CIRCUIT, "tran 1u 5m", ["v(oa)", "v(d)", "v(jn)", "v(jp)"])
    tail = [k for k, when in enumerate(t) if when >= 3e-3]
    swing = max(oa[k] for k in tail) - min(oa[k] for k in tail)
    clamp = max(d)
    n_gap = [jn[k] - oa[k] for k in tail]  # a follower source sits on the reverse-biased side
    p_gap = [oa[k] - jp[k] for k in tail]
    return [
        ("signal reaches the op-amp output", 1.0 < swing < 28.0, f"{swing:.3g} V p-p"),
        ("zener clamps the switch drain", 11.0 < clamp < 13.0, f"max {clamp:.3g} V"),
        ("N JFET source follows above its gate", 0 < min(n_gap) and max(n_gap) < 3.5, f"{min(n_gap):.3g} to {max(n_gap):.3g} V"),
        ("P JFET source follows below its gate", 0 < min(p_gap) and max(p_gap) < 3.5, f"{min(p_gap):.3g} to {max(p_gap):.3g} V"),
    ]
