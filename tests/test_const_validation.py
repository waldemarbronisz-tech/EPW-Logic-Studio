"""feat/const-property-validation — closes AUDIT_REPORT.md §10 pkt 1 ("Nadal
otwarte braki": Validator never checked const.*'s own property values).
ConstantBase.evaluate() (blocks/constants.py) only ever caught ValueError
around float()/int() — a property holding None/a list/a dict (impossible
through the property panel's own QDoubleSpinBox/QSpinBox, but not through a
hand-edited or corrupted .epwlogic file) raised an uncaught TypeError,
crashing the scan rather than falling back to the safe default. Validator
now rejects an unparseable const.real/const.int/const.time property, a
non-finite const.real value (NaN/Infinity), and a negative const.time
duration, all as compile ERRORS — the same "checked live in the UI, but ALSO
enforced at compile time" layering already applied to DI/DO/AI/AO addresses.
evaluate() itself now also catches TypeError alongside ValueError, so a block
evaluated outside the compiler (a stray script, a future caller) degrades to
the safe default instead of crashing.
"""
from logic_studio.core.project import Project
from logic_studio.compiler.core import Compiler
from logic_studio.compiler.validator import Validator
from logic_studio.blocks import register_builtin_blocks
from logic_studio.blocks.registry import BlockRegistry
from logic_studio.blocks.constants import RealConstant, IntConstant, TimeConstant

register_builtin_blocks()


def _errors_for(block):
    p = Project()
    p.add_block(block)
    errors, warnings = [], []
    Validator(p).run(errors, warnings)
    return errors


# ---- const.real -------------------------------------------------------

def test_const_real_valid_value_has_no_errors():
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = 3.14
    assert _errors_for(b) == []

def test_const_real_non_numeric_string_is_an_error():
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = "not a number"
    errors = _errors_for(b)
    assert any("REAL" in e and "poprawną liczbą" in e for e in errors)

def test_const_real_none_value_is_an_error_not_a_crash():
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = None
    errors = _errors_for(b)
    assert any("REAL" in e for e in errors)

def test_const_real_nan_is_an_error():
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = "nan"
    errors = _errors_for(b)
    assert any("skończoną" in e for e in errors)

def test_const_real_infinity_is_an_error():
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = float("inf")
    errors = _errors_for(b)
    assert any("skończoną" in e for e in errors)


# ---- const.int ----------------------------------------------------------

def test_const_int_valid_value_has_no_errors():
    b = BlockRegistry.create_block("const.int")
    b.properties["Value"] = 42
    assert _errors_for(b) == []

def test_const_int_non_numeric_string_is_an_error():
    b = BlockRegistry.create_block("const.int")
    b.properties["Value"] = "abc"
    errors = _errors_for(b)
    assert any("INT" in e and "poprawną liczbą całkowitą" in e for e in errors)

def test_const_int_list_value_is_an_error_not_a_crash():
    b = BlockRegistry.create_block("const.int")
    b.properties["Value"] = [1, 2]
    errors = _errors_for(b)
    assert any("INT" in e for e in errors)


# ---- const.time -----------------------------------------------------------

def test_const_time_valid_value_has_no_errors():
    b = BlockRegistry.create_block("const.time")
    b.properties["Time (ms)"] = 500
    assert _errors_for(b) == []

def test_const_time_zero_is_allowed():
    b = BlockRegistry.create_block("const.time")
    b.properties["Time (ms)"] = 0
    assert _errors_for(b) == []

def test_const_time_negative_is_an_error():
    b = BlockRegistry.create_block("const.time")
    b.properties["Time (ms)"] = -500
    errors = _errors_for(b)
    assert any("ujemny" in e for e in errors)

def test_const_time_non_numeric_is_an_error():
    b = BlockRegistry.create_block("const.time")
    b.properties["Time (ms)"] = "soon"
    errors = _errors_for(b)
    assert any("poprawną liczbą całkowitą" in e for e in errors)


# ---- Compilation actually fails on a bad const property -------------------

def test_compilation_fails_on_invalid_const_real():
    p = Project()
    b = BlockRegistry.create_block("const.real")
    b.properties["Value"] = "garbage"
    p.add_block(b)

    c = Compiler(p)
    assert c.compile() is None
    assert any("REAL" in e for e in c.errors)


# ---- evaluate() defense-in-depth: TypeError caught, never propagates ------

def test_real_constant_evaluate_survives_none_value():
    b = RealConstant()
    b.properties["Value"] = None
    b.evaluate()
    assert b.outputs[0].value == 0.0

def test_int_constant_evaluate_survives_list_value():
    b = IntConstant()
    b.properties["Value"] = [1, 2]
    b.evaluate()
    assert b.outputs[0].value == 0

def test_time_constant_evaluate_survives_none_value():
    b = TimeConstant()
    b.properties["Time (ms)"] = None
    b.evaluate()
    assert b.outputs[0].value == 1000
