#top=regfile::test

import cocotb
from spade import *
from cocotb.clock import Clock
import sys

def RegId(id) -> str:
    if id < 32:
        return f"RegId::Integer({id})"
    else:
        return f"RegId::Float({id - 32})"

def some(data) -> str:
    return f"Option::Some({data})"

def none() -> str:
    return "Option::None"

def t(*values) -> str:
    return f"({ ", ".join([str(v) for v in values]) })"

@cocotb.test()
async def basic_operation(dut):
    s = SpadeExt(dut)

    clk = dut.clk_i

    await cocotb.start(Clock(clk, 10, units='ns').start())

    await FallingEdge(clk)

    s.i.rs = RegId(0)
    s.i.rt = RegId(1)
    s.i.write = t(RegId(1), 0xdeadbeef)

    await FallingEdge(clk)

    s.o.assert_eq(t(0, 0))

    s.i.rs = RegId(0)
    s.i.rt = RegId(1)
    s.i.write = t(RegId(0), 0)

    await FallingEdge(clk)

    s.o.assert_eq(t(0, 0xdeadbeef))
