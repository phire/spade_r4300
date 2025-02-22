#top=regfile::test

import cocotb
from spade import *
from cocotb.clock import Clock
from cocotb.triggers import *

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

async def start(dut):
    s = SpadeExt(dut)

    phase1 = dut.phase1_i
    phase2 = dut.phase2_i
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
    s.i.write = t(RegId(0), 0)
    s.i.rs = RegId(0)
    s.i.rt = RegId(0)
    await RisingEdge(phase2)
    await RisingEdge(phase2)

    return (s, phase1, phase2)

@cocotb.test()
async def basic_operation(dut):
    s, phase1, phase2 = await start(dut)

    s.i.write = t(RegId(1), 0xdeadbeef)

    await RisingEdge(phase1)
    s.i.rs = RegId(0)
    s.i.rt = RegId(1)

    await RisingEdge(phase2)

    s.o.assert_eq(t(0, 0))
    s.i.rs = RegId(0)
    s.i.rt = RegId(0)

    await RisingEdge(phase1)

    s.i.rs = RegId(0)
    s.i.rt = RegId(1)

    await RisingEdge(phase2)

    s.o.assert_eq(t(0, 0xdeadbeef))
