#top=pipe::test_adder

import cocotb
from spade import *
from cocotb.clock import Clock

@cocotb.test()
async def simple_add(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)
    s.i.mode = "ExMode::Add64"

    s.i.x = "3"
    s.i.y = "4"
    await FallingEdge(clk)
    s.o.assert_eq("7")

    s.i.x = "0xdeadbeef"
    s.i.y = "0x11"
    await FallingEdge(clk)
    s.o.assert_eq("0xdeadbf00")

    s.i.x = "0x1111111111111111"
    s.i.y = "0x1111111111111111"
    await FallingEdge(clk)
    s.o.assert_eq("0x2222222222222222")

    s.i.x = "0xffffffffffffffff"
    s.i.y = "0x1"
    await FallingEdge(clk)
    s.o.assert_eq("0x0")

@cocotb.test()
async def simple_sub(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)

    s.i.mode = "ExMode::Sub64"
    s.i.x = "3"
    s.i.y = "4"
    await FallingEdge(clk)
    s.o.assert_eq("0xffff_ffff_ffff_ffff")

@cocotb.test()
async def setl(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)

    s.i.mode = "ExMode::SetLess"
    s.i.x = "3"
    s.i.y = "4"
    await FallingEdge(clk)
    s.o.assert_eq("1")

    s.i.x = "4"
    s.i.y = "3"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xdeadbeef"
    s.i.y = "0xdeadbeef"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xffffffffffffffff"
    s.i.y = "0x1"
    await FallingEdge(clk)
    s.o.assert_eq("1")

    s.i.x = "0xffffffffffffffff"
    s.i.y = "0xffffffffffffffff"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xffffffffffffffff"
    s.i.y = "0xfffffffffffffffe"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xfffffffffffffffe"
    s.i.y = "0xfffffffffffffff1"
    await FallingEdge(clk)
    s.o.assert_eq("0")

@cocotb.test()
async def setlu(dut):
    s = SpadeExt(dut)
    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())
    await FallingEdge(clk)

    s.i.mode = "ExMode::SetLessUnsigned"
    s.i.x = "3"
    s.i.y = "4"
    await FallingEdge(clk)
    s.o.assert_eq("1")

    s.i.x = "4"
    s.i.y = "3"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xdeadbeef"
    s.i.y = "0xdeadbeef"
    await FallingEdge(clk)
    s.o.assert_eq("0")

    s.i.x = "0xffffffffffffffff"
    s.i.y = "0x1"
    await FallingEdge(clk)
    s.o.assert_eq("0")
