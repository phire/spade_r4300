#top=dcache::mask_test

import cocotb
from spade import *
from cocotb.clock import Clock
from cocotb.triggers import *

def bitmask(size, align = None):
    mask = ((1 << (size + 1) * 8) - 1)

    if align is not None:
        return mask << ((7 - (align + size)) * 8)
    return mask

@cocotb.test()
async def mask_masking(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())

    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            dut._log.info(f"size: {size+1}, align: {align}")
            s.i.mask = f"MemMask({size}, {align})"
            s.i.mode = "MaskTestMode::Size"

            await FallingEdge(clk)
            assert s.o.value() == str(size + 1)

            s.i.mode = "MaskTestMode::ByteMask"
            expected_byte_mask = ((1 << (size + 1)) - 1) << (align)
            await FallingEdge(clk)
            assert bin(int(s.o.value())) == bin(expected_byte_mask)
            dut._log.info(f"byte_mask: {int(s.o.value()):08b}, expected: {expected_byte_mask:08b}")

            s.i.mode = "MaskTestMode::BitMask"
            expected_bit_mask = bitmask(size, align)
            await FallingEdge(clk)
            dut._log.info(f"bit_mask: {int(s.o.value()):016x}, expected: {expected_bit_mask:016x}")
            assert hex(int(s.o.value())) == hex(expected_bit_mask)

@cocotb.test()
async def mask_clear(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x1122334455667788

    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            dut._log.info(f"size: {size+1}, align: {align}")

            s.i.mask = f"MemMask({size}, {align})"
            s.i.mode = "MaskTestMode::Clear"
            mask = bitmask(size, align)
            expected = 0x1122334455667788 & ~(mask)

            await FallingEdge(clk)
            dut._log.info(f"result: {int(s.o.value()):016x}, expected: {expected:016x}, mask: {mask:016x}")
            assert hex(int(s.o.value())) == hex(expected)

@cocotb.test()
async def mask_extract(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x1122334455667788
    s.i.mode = "MaskTestMode::Extract"

    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            dut._log.info(f"size: {size+1}, align: {align}")
            s.i.mask = f"MemMask({size}, {align})"
            mask = bitmask(size)
            shift = ((7 - (align + size)) * 8)
            expected = (0x1122334455667788 >> shift) & mask

            await FallingEdge(clk)
            assert hex(int(s.o.value())) == hex(expected)
            dut._log.info(f"result: {int(s.o.value()):016x}, expected: {expected:016x}, shift: {shift}")

@cocotb.test()
async def mask_extract_signed(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x11223344F0000000

    s.i.mask = f"MemMask(3, 0)"
    s.i.mode = "MaskTestMode::Extract"

    await FallingEdge(clk)
    assert hex(int(s.o.value())) == hex(0x11223344)

    s.i.mode = "MaskTestMode::ExtractSigned"
    await FallingEdge(clk)
    assert hex(int(s.o.value())) == hex(0x11223344)

    s.i.mask = f"MemMask(3, 4)"
    s.i.mode = "MaskTestMode::Extract"
    await FallingEdge(clk)
    assert hex(int(s.o.value())) == hex(0xf0000000)

    s.i.mode = "MaskTestMode::ExtractSigned"
    await FallingEdge(clk)
    assert hex(int(s.o.value())) == hex(0xfffffffff0000000)


@cocotb.test()
async def mask_insert(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x1122334455667788
    s.i.b = 0x0099aabbccddeeff
    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            s.i.mask = f"MemMask({size}, {align})"
            s.i.mode = "MaskTestMode::Insert"

            mask = bitmask(size, align)
            shift = ((7 - (align + size)) * 8)
            expected = (0x1122334455667788 & ~mask) | ((0x0099aabbccddeeff << shift) & mask)

            await FallingEdge(clk)
            dut._log.info(f"size: {size+1}, align: {align}, mask: {mask:016x}, shift: {shift}")
            dut._log.info(f"result: {int(s.o.value()):016x}, expected: {expected:016x}")
            assert hex(int(s.o.value())) == hex(expected)

            s.i.mode = "MaskTestMode::InsertAligned"
            expected = (0x1122334455667788 & ~mask) | (0x0099aabbccddeeff & mask)

            await FallingEdge(clk)
            dut._log.info(f"aligned result: {int(s.o.value()):016x}, expected: {expected:016x}")
            assert hex(int(s.o.value())) == hex(expected)


@cocotb.test()
async def mask_bytemux(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x1122334455667788
    s.i.b = 0x0099aabbccddeeff
    s.i.mode = "MaskTestMode::ByteMux"

    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            s.i.mask = f"MemMask({size}, {align})"
            mask = bitmask(size, align)
            expected = (0x1122334455667788 & ~mask) | (0x0099aabbccddeeff & mask)

            await FallingEdge(clk)
            dut._log.info(f"size: {size+1}, align: {align}, mask: {mask:016x}")
            dut._log.info(f"aligned result: {int(s.o.value()):016x}, expected: {expected:016x}")
            assert hex(int(s.o.value())) == hex(expected)

    assert False


@cocotb.test()
async def mask_bytemux2(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    s.i.a = 0x1122334455667788
    s.i.b = 0x0099aabbccddeeff
    s.i.mode = "MaskTestMode::ByteMux2"

    # iterate though all possible sizes and alignments
    for size in range(8):
        for align in range(8 - size):
            s.i.mask = f"MemMask({size}, {align})"
            mask = bitmask(size, align)
            expected = (0x1122334455667788 & ~mask) | (0x0099aabbccddeeff & mask)

            await FallingEdge(clk)
            dut._log.info(f"size: {size+1}, align: {align}, mask: {mask:016x}")
            dut._log.info(f"aligned result: {int(s.o.value()):016x}, expected: {expected:016x}")
            assert hex(int(s.o.value())) == hex(expected)

    assert False
