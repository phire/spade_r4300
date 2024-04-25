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
        self.i.tag = hex(pc >> 12 & 0xfffff)
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


def rtype(op, rs, rt, rd, sh, func):
    return (op << 26) | (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | func

def itype(op, rs, rt, imm):
    return (op << 26) | (rs << 21) | (rt << 16) | (imm & 0xffff)

def jtype(op, addr):
    return (op << 26) | addr

def balways(pc, offset):
    offset = (offset >> 2) & 0xffff
    return itype(1, 0, 1, offset)

def nop(num=0):
    # addi $zero, $zero, num
    return itype(9, 0, 0, num)

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
        p.set_inst(nop(i), i << 2)
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index()}")
        assert p.next_pc() == pc
        pc = p.next_pc() + 4

@cocotb.test()
async def loop(dut):
    p = Pipeline(dut)
    await p.start()
    await p.clock()

    prog = [
        nop(),
        balways(0, -8),
        nop(),
        nop(),
        nop(),
        nop(),
    ]

    for _ in range(25):
        inst = prog[p.index() % len(prog)]
        p.set_inst(inst, p.next_pc())
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index():04x}, inst: {inst:08x}")
        assert p.index() < 3

@cocotb.test()
async def long_jump(dut):
    p = Pipeline(dut)
    await p.start()
    await p.clock()

    prog = [
        itype(0b001111, 0, 15, 0x00cc), # lui $at, 0x00cc
        nop(2),
        nop(3),
        nop(4),
        itype(0b001101, 15, 15, 0xbba0), # ori $at, $at, 0x00cc
        nop(6),
        nop(7),
        nop(8),
        rtype(0, 15, 0, 0, 0, 0b001000), # jr $at
        nop(10),
    ]

    for inst in prog:
        p.set_inst(inst, p.next_pc())
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index():04x}, inst: {inst:08x}")


    if p.next_pc() != 0x00ccbba0:
        raise Exception(f"Expected pc: 0x00ccbba0, found: 0x{p.next_pc():08x}")

