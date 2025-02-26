#top=dcache::test_harness

import cocotb
from spade import *
from cocotb.clock import Clock
from cocotb.triggers import *

def some(data) -> str:
    return f"Option::Some({data})"

def none() -> str:
    return "Option::None"

def t(*values) -> str:
    return f"({ ", ".join([str(v) for v in values]) })"

def hash(line, word) -> int:
    return (line << 21 | 0x3000 | line << 5 | word) & 0xffff_ffff

class DCache:
    def __init__(self, dut):
        self.dut = dut
        self.s = SpadeExt(dut)
        self.i = self.s.i
        self.o = self.s.o

        self.i.index = 0
        self.i.fill = none()
        self.i.write = none()
        self.i.read_en = False
        self.clk = self.dut.clk_i

    async def start(self):
        await cocotb.start(Clock(self.clk, 10, units='ns').start())
        await FallingEdge(self.clk)

        return self.clk

    async def fill(self, line, tag, data):
        self.i.fill = some(t(line, tag, data))
        await FallingEdge(self.clk)
        self.i.fill = none()

    async def read(self, index):
        self.i.index = index
        self.i.read_en = True
        await FallingEdge(self.clk)
        self.i.read_en = False

    async def write(self, data):
        self.i.write = some(data)
        await FallingEdge(self.clk)
        self.i.write = none()


@cocotb.test()
async def dcache_read(dut):
    s = DCache(dut)
    clk = await s.start()

    # Put something in the cache
    await s.fill(0x18 >> 1, 0xcab77, "0xcafefeeddead8888beefcafe")
    await s.fill(0x20 >> 1 , 0xbba, 42)

    await FallingEdge(clk)

    # And read it back
    await s.read(0x18)
    dut._log.info(f"Read data: {s.o.value()} {int(s.o.data.value()):x}")
    s.o.assert_eq("DResult$(data: 0xcafefeed, tag: DTag$(tag: 0xcab77, valid: true, dirty: false), busy: false)")

    await s.read(0x19)
    s.o.assert_eq("DResult$(data: 0xdead8888beefcafe, tag: DTag$(tag: 0xcab77, valid: true, dirty: false), busy: false)")

    await s.read(0x21)
    s.o.assert_eq("DResult$(data: 42, tag: DTag$(tag: 0xbba, valid: true, dirty: false), busy: false)")

@cocotb.test()
async def dcache_write(dut):
    s = DCache(dut)
    clk = await s.start()

    # Put something in the cache
    await s.fill(0x18 >> 1, 0xcab77, "0xcafefeeddead8888beefcafe")

    await FallingEdge(clk)
    await FallingEdge(clk)

    # overwrite it
    await s.read(0x18)
    s.o.busy.assert_eq("false")
    await s.write("0xaa00aa00bb00cc")
    s.o.busy.assert_eq("true")

    await FallingEdge(clk)
    s.o.busy.assert_eq("false")

    await FallingEdge(clk)

    # And read it back
    await s.read(0x18)

    s.o.assert_eq("DResult$(data: 0xaa00aa00bb00cc, tag: DTag$(tag: 0xcab77, valid: true, dirty: true), busy: false)")

    await s.read(0x19)
    s.o.assert_eq("DResult$(data: 0xdead8888beefcafe, tag: DTag$(tag: 0xcab77, valid: true, dirty: true), busy: false)")
