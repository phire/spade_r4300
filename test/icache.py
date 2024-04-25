#top=icache::icache_test_harness

import cocotb
from spade import *
from cocotb.clock import Clock

def some(data) -> str:
    return f"Option::Some({data})"

def none() -> str:
    return "Option::None"

def t(*values) -> str:
    return f"({ ", ".join([str(v) for v in values]) })"

def hash(line, word) -> int:
    return (line << 21 | 0x3000 | line << 5 | word) & 0xffff_ffff

@cocotb.test()
async def basic_check(dut):
    s = SpadeExt(dut)

    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.addr = "0x0"
    s.i.write = none()
    await FallingEdge(clk)

    # write something to the cache

    s.i.write = some(t(0x18 >> 3, 0xcab77,"0xdead8888beefcafe"))
    await FallingEdge(clk)

    s.i.write = none()
    await FallingEdge(clk)

    # And read it back
    s.i.addr = "0x18"
    await FallingEdge(clk)
    s.i.addr = "0x1c"
    s.o.assert_eq(t("0xbeefcafe", "0xcab77", "true"))
    await FallingEdge(clk)
    s.o.assert_eq(t("0xdead8888", "0xcab77", "true"))

#@cocotb.test()
async def sequential(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.addr = "0x0"
    s.i.write = none()

    await FallingEdge(clk)

    # start by filling entire cache with test pattern
    for line in range(128):
        tag = line | (0xdd << 10)
        for w in (0, 2, 4, 6):
            addr = (w >> 1) | (line << 2)
            data = (hash(line, w + 1) << 32) | hash(line, w)

            s.i.write = some(t(addr, tag, data))
            await FallingEdge(clk)

    s.i.write = none()
    fails = []

    # verify it all with sequential reads
    for line in range(128):
        tag = line | (0xdd << 10)
        for w in range(8):
            addr = w << 2 | line << 5
            data = hash(line, w)

            s.i.addr = str(hex(addr))
            await FallingEdge(clk)

            if not s.o.is_eq(t(hex(data), hex(tag), "true")):
                fails.append((line, w, s.o))

    if fails:
        for line, w, o in fails:
            dut._log.error(f"line {line}, {w} failed: {str(o.value())}")
        dut._log.error(f"failed {len(fails)} times")
        assert False

@cocotb.test()
async def random(dut):
    s = SpadeExt(dut)

    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)

    # fill some test pattern with test pattern
    for line in range(12):
        tag = line
        for w in (0, 2, 4, 6):
            addr = w >> 1 | line << 2
            data = (hash(line, w + 1) << 32) | hash(line, w)
            s.i.write = some(t(addr, tag, data))
            await FallingEdge(clk)

    s.i.write = none()

    # visit in a random order
    for i in [0, 17, 27, 88, 89, 90, 89, 88, 87, 86, 10, 11, 12, 13, 15, 17, 18, 20]:
        line = i >> 3
        w = i & 7
        s.i.addr = str(hex(line << 5 | w << 2))
        await FallingEdge(clk)
        s.o.assert_eq(t(hex(hash(line, w)), line, "true"))
