#top=cpu

import cocotb
from spade import *
from cocotb.clock import Clock
from cocotb.triggers import *

class Core:
    def __init__(self, dut):
        self.dut = dut
        self.s = SpadeExt(dut)
        self.i = self.s.i
        self.o = self.s.o

        self.phase1 = dut.phase1_i
        self.phase2 = dut.phase2_i

    def next_pc(self):
        try:
            return int(self.o.pc.value(), 10)
        except:
            return 0xffffffff

    def status(self):
        return self.o.status.value()

    def external_write(self):
        if self.o.external.write == False:
            return None
        addr = int(self.o.external.addr.value())
        size = 1 + int(self.o.external.size.value())
        mask = (1 << size * 8) - 1
        data = int(self.o.external.data.value())
        return (addr, data & mask)

    async def start(self, icache, dcache):
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
        self.i.rst = True
        self.i.icache_write = "None"
        self.i.dcache_write = "None"

        for _ in range(3):
            await self.clock()


        # load data into icache
        for addr, data in icache:
            index = (addr >> 3) & 0x7ff
            tag = (addr >> 12) & 0xfffff
            self.dut._log.info(f"writing {hex(addr)} to icache")

            self.i.icache_write = f"Some(({index}, {tag}, {data}))"
            await self.clock()

        self.i.icache_write = "None"

        # and dcache
        for addr, data in dcache:
            index = (addr >> 4) & 0xff
            tag = (addr >> 12) & 0xfffff

            self.i.dcache_write = f"Some(({index}, {tag}, {data}))"
            await self.clock()

        self.i.dcache_write = "None"
        for _ in range(5):
            await self.clock()

        self.i.rst = "false"

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
async def core_external_write(dut):
    c = Core(dut)

    prog = [
        lui(2, 0xa000),
        lui(7, 0xdead),
        ori(7, 7, 0xbeef),
        itype(0b101011, 2, 7, 0x0044), # sw $r7, 0x44($r2)
        nop(),
        nop(),
        nop(),
        nop(),
        nop(),
    ]

    if len(prog) % 2:
        prog.append(nop())

    # pack into 64-bit words
    icache = [(0xbfc00000 + i * 4, prog[i] << 32 | (prog[i+1])) for i in range(0, len(prog), 2)]
    dcache = [(0x00010000 + i, 0) for i in range(0, 0x100, 16)]

    await c.start(icache, dcache)

    for _ in range(20):
        await c.clock()
        dut._log.info(f"pc: {hex(c.next_pc())}, {c.o.external.value()}")
        write = c.external_write()
        if write is not None:
            addr, data = write
            assert addr == 0x00000044, f"addr: {hex(addr)}"
            assert data == 0xdeadbeef, f"data: {hex(data)}"
            return

    assert False, "no write"
