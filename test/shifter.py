#top=pipe::test_shifter

import cocotb
from spade import *
from cocotb.clock import Clock

async def start(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i
    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)

    return s, clk

async def do_shift(s, clk, val, shift, expected):
    s.i.add_result = str(shift)
    s.i.shift_mux = hex(val)
    await FallingEdge(clk)
    s.o.assert_eq(hex(expected))


@cocotb.test()
async def shift_left(dut):
    s, clk = await start(dut)

    s.i.mode = "ExMode::ShiftLeft"
    # s.i.add_result = "3"
    # s.i.shift_mux = "1"
    # await FallingEdge(clk)
    # s.o.assert_eq("8")
    await do_shift(s, clk, 1, 3, 8)


    # s.i.shift_mux = "0x10000001"
    # s.i.add_result = "4"
    # await FallingEdge(clk)
    # s.o.assert_eq("0x100000010")
    await do_shift(s, clk, 0x10000001, 4, 0x100000010)

    # shift amounts should be truncated to five bits
    # s.i.add_result = "33"
    # s.i.shift_mux = "1"
    # await FallingEdge(clk)
    # s.o.assert_eq("2")
    await do_shift(s, clk, 1, 33, 0x2)

    # or 6 bits when doing a shift by 64

    s.i.mode = "ExMode::ShiftLeft64"
    await do_shift(s, clk, 1, 33, 0x200000000)

@cocotb.test()
async def shift_right(dut):
    s, clk = await start(dut)

    s.i.mode = "ExMode::ShiftRight"
    await do_shift(s, clk, 8, 3, 1)

    # check that it will cross 32bit boundaries
    await do_shift(s, clk, 0x100000010, 4, 0x10000001)

    # shift amounts should be truncated to five bits
    await do_shift(s, clk, 8, 34, 2)

    # or 6 bits when doing a shift by 64
    s.i.mode = "ExMode::ShiftRight64"
    await do_shift(s, clk, 0x200000002, 33, 1)

@cocotb.test()
async def shift_right_arith(dut):
    s, clk = await start(dut)

    s.i.mode = "ExMode::ShiftRightArith"
    await do_shift(s, clk, 8, 3, 1)

    # check that it will cross 32bit boundaries
    await do_shift(s, clk, 0x100000010, 4, 0x10000001)

    # shift amounts should be truncated to five bits
    await do_shift(s, clk, 8, 34, 2)

    # or 6 bits when doing a shift by 64
    s.i.mode = "ExMode::ShiftRightArith64"
    await do_shift(s, clk, 0x200000002, 33, 1)

    # check sign extention behavior
    await do_shift(s, clk, 0x8000_0000_0000_0000, 8, 0xff80_0000_0000_0000)

    # and with a 32bit shift
    s.i.mode = "ExMode::ShiftRightArith"
    await do_shift(s, clk, 0x8000_0000_0000_0000, 32 + 9, 0xffc0_0000_0000_0000)
