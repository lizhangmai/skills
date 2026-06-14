* RC Low-pass Filter - HSpice format for XDM smoke testing
.TITLE RC Low-pass Filter

V1 in 0 PULSE 0 1 0 1n 1n 5u 10u
R1 in out 1k
C1 out 0 1n

.TRAN 10n 20u
.PROBE V(out)

.END
