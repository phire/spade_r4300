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

    def set_inst(self, inst):
        self.i.ins = hex(inst)
        self.i.tag = hex((self.next_pc() >> 12) & 0xfffff)
        self.i.valid = "true"

    def next_pc(self):
        try:
            return int(self.o.next_pc.value(), 10)
        except:
            return 0xffffffff

    def d_index(self):
        val = self.o.d_index.value()
        if val.startswith("Some("):
            return int(val[5:-1], 10)
        return None

    def write_mask(self):
        if self.o.write_en.value() == "true":
            size = int(self.o.write_mask.size.value())
            align = int(self.o.write_mask.align.value())
            left = ((7 - size) - align) << 3
            return (0xffffffff_ffffffff >> ((7 - size) << 3)) << left

        return None

    def w_mask_details(self):
        return self.o.write_mask.size.value(), self.o.write_mask.align.value(), self.o.write_en.value()

    def write(self):
        try:
            return int(self.o.write.value(), 10)
        except:
            return 0

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
        await self.clock()

    async def halfclock(self):
        await FallingEdge(self.phase1)

    async def clock(self):
        await FallingEdge(self.phase2)


def rtype(op, rs, rt, rd, sh, func):
    assert func <= 0x3f
    return (op << 26) | (rs << 21) | (rt << 16) | (rd << 11) | (sh << 6) | func

def itype(op, rs, rt, imm):
    assert imm <= 0xffff
    return (op << 26) | (rs << 21) | (rt << 16) | (imm)

def jtype(op, addr):
    return (op << 26) | addr

def balways(pc, offset):
    offset = (offset >> 2) & 0xffff
    return itype(1, 0, 1, offset)

def nop(num=0):
    # addi $zero, $zero, num
    return itype(9, 0, 0, num)

def lui(rt, imm):
    assert imm < 0x10000
    return itype(0b001111, 0, rt, imm)

def ori(rt, rs, imm):
    assert imm < 0x10000
    return itype(0b001101, rs, rt, imm)

def li(rt, imm):
    return ori(rt, 0, imm)

def lwi(rd, imm):
    return [lui(rd, imm >> 16), ori(rd, rd, imm & 0xffff)]



@cocotb.test()
async def test_pc(dut):
    """Tests that the pipeline comes out of reset and increments pc"""
    p = Pipeline(dut)
    await p.start()
    p.set_inst(0)

    # reset vector
    pc = 0xffffffffbfc00000

    # check that pc increments starting from reset vector
    for i in range(20):
        p.set_inst(nop(i))
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index()}")
        assert p.next_pc() == pc
        pc = p.next_pc() + 4

@cocotb.test()
async def loop(dut):
    p = Pipeline(dut)
    await p.start()

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
        p.set_inst(inst)
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index():04x}, inst: {inst:08x}")
        assert p.index() < 3

@cocotb.test()
async def long_jump(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        itype(0b001111, 0, 15, 0x00cc), # lui $r15, 0x00cc
        nop(2),
        nop(3),
        nop(4),
        itype(0b001101, 15, 15, 0xbba0), # ori $r15, $r15, 0x00cc
        nop(6),
        nop(7),
        nop(8),
        rtype(0, 15, 0, 0, 0, 0b001000), # jr $r15
        nop(10),
    ]

    for inst in prog:
        p.set_inst(inst)
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index():04x}, inst: {inst:08x}")

    if p.next_pc() != 0x00ccbba0:
        raise Exception(f"Expected pc: 0x00ccbba0, found: 0x{p.next_pc():08x}")

async def do_stores(p, prog, dut, loads=dict()):
    open_row = None
    writes = []

    for inst in prog:
        p.set_inst(inst)
        await p.clock()
        dut._log.info(f"index: {p.index():04x}, inst: {inst:08x}, mask: {p.w_mask_details()}")

        if p.write_mask() is not None:
            dut._log.info(f"writing: {p.write():x} to {open_row << 3:x} with mask: {p.write_mask():x}")
            writes.append((open_row, p.write_mask(), p.write()))

        index = p.d_index()

        if index is not None:
            dut._log.info(f"opening row {index:x} (addr: {index << 3:x})")
            try:
                p.i.data = hex(loads[index << 3])
            except:
                p.i.data = "0x55aa55aa55aa55aa"
            p.i.d_tag = "0"
            p.i.d_valid = "true"
            open_row = p.d_index()
        else:
            open_row = None
            p.i.d_valid = "false"

    return writes


@cocotb.test()
async def store_word(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(7, 0xdead),
        nop(),
        nop(),
        nop(),
        ori(7, 7, 0xbeef),
        nop(),
        nop(),
        nop(),
        itype(0b101011, 0, 7, 0x0044), # sw $r7, 0x44($zero)
        itype(0b101011, 0, 7, 0x0268), # sw $r7, 0x268($zero)
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut)


    assert writes, "No write found"

    row, mask, data = writes[0]
    addr = row << 3
    assert addr == 0x40
    assert mask == 0x00000000ffffffff
    assert data & mask == 0x00000000deadbeef

    row, mask, data = writes[1]
    addr = row << 3
    assert addr == 0x268
    assert mask == 0xffffffff00000000
    assert data & mask == 0xdeadbeef00000000

@cocotb.test()
async def store_byte(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(7, 0xdead),
        nop(),
        nop(),
        nop(),
        ori(7, 7, 0xbeef),
        nop(),
        nop(),
        nop(),
        itype(0b101000, 0, 7, 0x50), # sb $r7, 0x50($zero)
        itype(0b101000, 0, 7, 0x51), # sb $r7, 0x51($zero)
        itype(0b101000, 0, 7, 0x52), # sb $r7, 0x52($zero)
        itype(0b101000, 0, 7, 0x53), # sb $r7, 0x53($zero)
        itype(0b101000, 0, 7, 0x54), # sb $r7, 0x54($zero)
        itype(0b101000, 0, 7, 0x55), # sb $r7, 0x55($zero)
        itype(0b101000, 0, 7, 0x56), # sb $r7, 0x56($zero)
        itype(0b101000, 0, 7, 0x57), # sb $r7, 0x57($zero)
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut)

    assert writes, "No write found"

    for i in range(8):
        row, mask, data = writes[i]
        dut._log.info(f"byte: {i}, mask: {mask:x}, data: {data:x}")
        assert row << 3 == 0x50
        assert mask == (0xff000000_00000000 >> (i * 8))
        assert (data & mask) == (0xef000000_00000000 >> (i * 8))

@cocotb.test()
async def load_word(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        # load a word
        itype(0b100011, 0, 3, 0x0030), # lw $r3, 0x30($zero)
        nop(),
        nop(),
        nop(),
        # and store it back
        itype(0b101011, 0, 3, 0x0074), # sw $r3, 0x70($zero)
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut, {0x30: 0x00000000fccffccf})

    assert writes, "No write found"

    row, mask, data = writes[0]
    addr = row << 3
    dut._log.info(f"addr: {addr:x}, mask: {mask:x}, data: {data:x}")
    assert addr == 0x70
    assert mask == 0x00000000ffffffff
    assert data & mask == 0x00000000fccffccf
