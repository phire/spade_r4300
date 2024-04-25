#top=pipe::test_pipeline

import cocotb
from spade import *
from cocotb.clock import Clock

class Pipeline:
    def __init__(self, dut):
        self.dut = dut
        self.s = SpadeExt(dut)
        self.i = self.s.i
        self.o = self.s.o

        self.phase1 = dut.phase1_i
        self.phase2 = dut.phase2_i

    def set_inst(self, inst, pc):
        self.i.ins = hex(inst)
        self.i.tag = hex(pc >> 12)
        self.i.valid = "true"

    def next_pc(self):
        try:
            return int(self.o.next_pc.value(), 10)
        except:
            return 0xffffffff

    def index(self):
        try:
            return int(self.o.index.value(), 10)
        except:
            return 0xfff

    async def start(self):
        phase1 = self.phase1
        phase2 = self.phase2
        async def custom_clock():
            # pre-construct triggers for performance
            time = Timer(10, units="ps")
            await Timer(5, units="ps")
            while True:
                phase1.value = 1
                phase2.value = 0
                await time
                phase1.value = 0
                phase2.value = 1
                await time

        await cocotb.start(custom_clock())

        # reset
        self.i.rst = "true"
        await self.clock()
        await self.clock()
        self.i.rst = "false"

    async def halfclock(self):
        await FallingEdge(self.phase1)

    async def clock(self):
        await FallingEdge(self.phase2)


@cocotb.test()
async def test_pc(dut):
    """Tests that the pipeline comes out of reset and increments pc"""
    p = Pipeline(dut)
    await p.start()
    p.set_inst(0, 0)
    await p.clock()

    # reset vector
    pc = 0xffffffffbfc00000

    # check that pc increments starting from reset vector
    for i in range(20):
        p.set_inst(i, i << 2)
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index()}")
        assert p.next_pc() == pc + 4
        pc = p.next_pc()
