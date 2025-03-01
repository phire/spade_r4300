#top=pipe::test_pipeline

import cocotb
from spade import *
from cocotb.clock import Clock
from cocotb.triggers import *

class Pipeline:
    def __init__(self, dut):
        self.dut = dut
        self.s = SpadeExt(dut)
        self.i = self.s.i
        self.o = self.s.o

        self.phase1 = dut.phase1_i
        self.phase2 = dut.phase2_i

    def set_inst(self, inst, tag=None, valid=True):
        if tag is None:
            tag = (self.next_pc() >> 12) & 0xfffff

        self.i.ins = hex(inst)
        self.i.tag = hex(tag)
        self.i.valid = "true" if valid else "false"

    def next_pc(self):
        try:
            return int(self.o.next_pc.value(), 10)
        except:
            return 0xffffffff

    def d_index(self):
        if self.o.d_index_valid.value() == "true":
            val = self.o.d_index.value()
            return int(val, 10)
        return None

    def is_write(self):
        return self.o.write_en.value() == "true"

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

    def status(self):
        return self.o.status.value()

    def fetch_en(self):
        return self.o.fetch_en.value() == "true"

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
        self.i.ins = "0"
        self.i.tag = "0"
        self.i.valid = "false"
        self.i.data = "0"
        self.i.d_tag = "0"
        self.i.d_valid = "false"
        self.set_inst(0)

        for _ in range(10):
            await self.clock()

        self.i.rst = "false"
        await self.clock()

    async def halfclock(self):
        await RisingEdge(self.phase1)

    async def clock(self):
        await RisingEdge(self.phase2)


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

    # reset vector
    pc = 0xffffffffbfc00000
    dut._log.info(f"pc: {p.next_pc():x} index: {p.index()}")

    assert p.next_pc() == pc
    p.set_inst(0)

    # check that pc increments starting from reset vector
    for i in range(20):
        p.set_inst(nop(i))
        pc = p.next_pc() + 4
        await p.clock()
        dut._log.info(f"pc: {p.next_pc():x} index: {p.index()}")
        assert p.next_pc() == pc

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
        itype(0b001101, 15, 15, 0xbba0), # ori $r15, $r15, 0xbba0
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

    timeout = 1000

    for _ in range(1000):
        # simulate icache reads as completing halfway though the cycle
        if p.phase1.value == 0:
            p.i.ins = 0
            await p.halfclock()

        pc_index = p.index()
        if pc_index >= len(prog):
            dut._log.info(f"index: {pc_index:04x}, inst: [end], status: {p.status()}")
            return writes
        inst = prog[pc_index]

        p.set_inst(inst)
        await p.clock()

        dut._log.info(f"index: {pc_index:04x}, inst: {inst:08x}, status: {p.status()}")

        assert p.status() in ["Ok()", "Stall(LoadInterlock())", "Stall(DataCacheBusy())", "ExceptionWB(Reset())"]

        if p.is_write():
            if p.open_row is None:
                dut._log.info(f"writing: {p.write():x} after row closed")
            else:
                dut._log.info(f"writing: {p.write():x} to {p.open_row << 3:x}")
                writes.append((p.open_row, p.write()))
                p.open_row = None
            continue

        index = p.d_index()

        if index is not None:
            dut._log.info(f"opening row {index:x} (addr: {index << 3:x})")
            try:
                p.i.data = hex(loads[index << 3])
            except:
                p.i.data = "0x1122334455667788"
            p.i.d_tag = "0"
            p.i.d_valid = "true"
            p.open_row = p.d_index()

    raise Exception("Timeout")

@cocotb.test()
async def store_word(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(7, 0xdead),
        ori(7, 7, 0xbeef),
        itype(0b101011, 0, 7, 0x0044), # sw $r7, 0x44($zero)
        nop(),
        itype(0b101011, 0, 7, 0x0268), # sw $r7, 0x268($zero)
        nop(),
        nop(),
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut)

    assert writes, "No write found"

    row, data = writes[0]
    addr = row << 3
    dut._log.info(f"word: {addr}, data: {data:x}")
    assert addr == 0x40
    assert data == 0x11223344deadbeef

    row, data = writes[1]
    addr = row << 3
    dut._log.info(f"word: {addr}, data: {data:x}")
    assert addr == 0x268
    assert data == 0xdeadbeef55667788

@cocotb.test()
async def store_byte(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(7, 0xdead),
        ori(7, 7, 0xbeef),
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
        nop(),
    ]

    writes = await do_stores(p, prog, dut)

    assert writes, "No write found"

    for i in range(8):
        row, data = writes[i]
        dut._log.info(f"byte: {i}, data: {data:x}")

        mask = 0xff000000_00000000 >> (i * 8)
        expected = 0x1122334455667788 & ~mask | (0xef000000_00000000 >> (i * 8))

        assert row << 3 == 0x50
        assert data == expected

@cocotb.test()
async def load_word(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        # load a word
        itype(0b100011, 0, 3, 0x0030), # lw $r3, 0x30($zero)
        nop(),
        # and store it back
        itype(0b101011, 0, 3, 0x0074), # sw $r3, 0x74($zero)
        nop(1),
        nop(2),
        nop(3),
        nop(4),
    ]

    writes = await do_stores(p, prog, dut, {0x30: 0xfccffccf00000000})

    assert writes, "No write found"

    row, data = writes[0]
    addr = row << 3
    dut._log.info(f"addr: {addr:x}, data: {data:x}")
    assert addr == 0x70
    assert data == 0x11223344fccffccf


@cocotb.test()
async def load_word_upper(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        # load a word
        itype(0b100011, 0, 3, 0x0034), # lw $r3, 0x34($zero)
        nop(),
        # and store it back
        itype(0b101011, 0, 3, 0x0074), # sw $r3, 0x74($zero)
        nop(1),
        nop(2),
        nop(3),
        nop(4),
    ]

    writes = await do_stores(p, prog, dut, {0x30: 0x00000000fccffccf})

    assert writes, "No write found"

    row, data = writes[0]
    addr = row << 3
    dut._log.info(f"addr: {addr:x}, data: {data:x}")
    assert addr == 0x70
    assert data == 0x11223344fccffccf

@cocotb.test()
async def load_interlock(dut):
    """Same as load_word, but without the nop"""
    p = Pipeline(dut)
    await p.start()

    prog = [
        # load a word
        itype(0b100011, 0, 3, 0x0034), # lw $r3, 0x30($zero)
        # and store it back
        itype(0b101011, 0, 3, 0x0074), # sw $r3, 0x74($zero)
        nop(1),
        nop(2),
        nop(3),
        nop(4),
    ]

    writes = await do_stores(p, prog, dut, {0x30: 0x00000000fccffccf})

    assert writes, "No write found"

    row, data = writes[0]
    addr = row << 3
    dut._log.info(f"addr: {addr:x}, data: {data:x}")
    assert data & 0xffffffff == 0xfccffccf

@cocotb.test()
async def dcache_busy(dut):
    """A load following a store should stall for one cycle"""
    p = Pipeline(dut)
    await p.start()

    prog = [
        # store
        *lwi(3, 0xdeadbeef),
        itype(0b101011, 0, 3, 0x0074), # sw $r3, 0x74($zero)
        # back to back stores
        itype(0b101000, 0, 3, 0x0076), # sb $r3, 0x78($zero)
        # then a load
        itype(0b100011, 0, 3, 0x0034), # lw $r3, 0x30($zero)
        nop(1),
    ]

    writes = await do_stores(p, prog[:-2], dut)
    assert writes == []
    assert p.status() == "Stall(DataCacheBusy())"

    writes = await do_stores(p, prog[:-1], dut)
    assert writes == [(0x70 >> 3, 0x11223344deadbeef)]
    assert p.status() == "Stall(DataCacheBusy())"

    # make sure it clears
    writes = await do_stores(p, prog, dut)
    assert writes == [(0x70 >> 3, 0x112233445566ef88)]


    assert p.status() == "Ok()"

@cocotb.test()
async def store_interlock(dut):
    """Same as store_word, but without the nop"""

    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(7, 0xdead),
        ori(7, 7, 0xbeef),
        itype(0b101011, 0, 7, 0x0044), # sw $r7, 0x44($zero)
        itype(0b101011, 0, 7, 0x0268), # sw $r7, 0x268($zero)
        nop(),
        nop(),
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut)

    assert writes, "No write found"

    row, data = writes[0]
    addr = row << 3
    dut._log.info(f"word: {addr}, data: {data:x}")
    assert addr == 0x40
    assert data == 0x11223344deadbeef

    row, data = writes[1]
    addr = row << 3
    dut._log.info(f"word: {addr}, data: {data:x}")
    assert addr == 0x268
    assert data == 0xdeadbeef55667788

@cocotb.test()
async def bypassing(dut):
    """This test is worth it's weight in gold"""
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(8, 0xdead),
        ori(7, 8, 0xbeef),
        # these ORI instructions test bypassing on RS
        ori(1, 7, 0), # bypass RS from EX
        ori(2, 7, 0), # bypass RS from DC
        ori(3, 7, 0), # same-cycle regfile write and read
        ori(4, 7, 0), # normal, RS from regfile
        # these stores should all read from regfile
        itype(0b101011, 0, 1, 0x54), # sw $r1, 0x54($zero)
        itype(0b101011, 0, 2, 0x64), # sw $r2, 0x64($zero)
        itype(0b101011, 0, 3, 0x74), # sw $r3, 0x74($zero)
        itype(0b101011, 0, 4, 0x84), # sw $r4, 0x84($zero)
        ori(9, 8, 0xbeef),
        # and these stores are bypassing on RT from the ori above
        # bypass RT from EX
        itype(0b101011, 0, 9, 0x54), # sw $r7, 0x54($zero)
        # bypass RT from DC
        itype(0b101011, 0, 9, 0x64), # sw $r7, 0x64($zero)
        # same-cycle regfile write and read
        itype(0b101011, 0, 9, 0x74), # sw $r7, 0x74($zero)
        # normal, RT from regfile
        itype(0b101011, 0, 9, 0x84), # sw $r7, 0x84($zero)
        nop(),
        nop(),
        nop(),
    ]

    writes = await do_stores(p, prog, dut)
    for i in range(8):
        row, data = writes[i]
        dut._log.info(f"byte: {i}, data: {data:x}")
        assert data & 0xffffffff == 0xdeadbeef, f"for write {i} Expected 0xdeadbeef, found: {data:x}"

@cocotb.test()
async def icache(dut):
    p = Pipeline(dut)
    await p.start()

    jump = [
        itype(0b001111, 0, 15, 0x2222), # lui $r15, 0x2222
        itype(0b001101, 15, 15, 0x2220), # ori $r15, $r15, 0x2220
        rtype(0, 15, 0, 0, 0, 0b001000), # jr $r15
        nop(10),
    ]
    await do_stores(p, jump, dut)
    assert p.next_pc() == 0x22222220

    # should stall if invalid
    p.set_inst(nop(0xeee), valid=False)
    await p.clock()
    dut._log.info(f"pc: {p.next_pc():x}, status: {p.status()}")
    assert p.status() == "Stall(InstructionCacheBusy())"

    # valid with correct tag... shouldn't stall
    p.set_inst(nop(0xddd), tag=0x22222, valid=True)
    await p.clock()
    dut._log.info(f"pc: {p.next_pc():x}, status: {p.status()}")
    assert p.status() == "Ok()"

    # valid with incorrect tag... should stall
    p.set_inst(nop(0xccc), tag=0x33333, valid=True)
    await p.clock()
    dut._log.info(f"pc: {p.next_pc():x}, status: {p.status()}")
    assert p.status() == "Stall(InstructionCacheBusy())"

@cocotb.test()
async def dcache_miss(dut):
    p = Pipeline(dut)
    await p.start()
    p.set_inst(0)
    timeout = 20

    while not p.fetch_en():
        await p.clock()
        if timeout == 0:
            raise Exception("Timeout")
        timeout -= 1

    assert p.fetch_en() and p.index() == 0

    p.set_inst(itype(0b101011, 0, 0, 0x54)) # sw $zero, 0x54($zero)

    await p.clock()
    await p.halfclock()
    assert p.fetch_en() and p.index() == 1

    p.set_inst(nop())
    assert p.status() == "Ok()"
    await p.clock()
    assert p.status() == "Ok()"
    await p.clock()
    # make sure the pipeline misses
    assert p.status() == "Stall(DataCacheMiss())"

    # and stays missed
    # todo: This should switch to DataCacheBusy after one cycle
    for i in range(10):
        await p.clock()
        assert p.status() == "Stall(DataCacheMiss())"
        assert p.index() == 2
        assert not p.fetch_en()

    p.i.d_valid = "true"
    p.i.data = "0xdeadbeefdeadbeef"
    p.i.d_tag = "0"

    await p.clock()

    # and then comes out of miss
    assert p.status() == "Ok()"

@cocotb.test()
async def external_write(dut):
    p = Pipeline(dut)
    await p.start()

    prog = [
        lui(2, 0xa000),
        lui(7, 0xdead),
        ori(7, 7, 0xbeef),
        itype(0b101011, 2, 7, 0x0044), # sw $r7, 0x44($r2)
        nop(),
        nop(),
        nop(),
    ]

    for inst in prog:
        p.set_inst(inst)
        await p.clock()
        dut._log.info(f"{p.status()} {int(p.o.external.addr.value()):x} {int(p.o.external.data.value()):x}")

    p.o.external.assert_eq("ExternalRequest$(addr: 0x44, data: 0xffffffffdeadbeef, size: 3, write: true)")
