from dryer.extract import entries_in_source


def spans(source: str) -> list[tuple[int, int]]:
    entries, warning = entries_in_source("kotlin", source, "Demo.kt", "Demo.kt")
    assert warning is None
    return [(entry.start_line, entry.end_line) for entry in entries]


def test_top_level_member_and_interface_functions_with_a_body_are_units():
    source = """\
fun top(x: Int): Int {
    return x
}

class Box {
    fun member(x: Int) = x + 1
}

interface Shape {
    fun area(): Int
    fun twice(): Int { return area() * 2 }
}
"""
    assert spans(source) == [(1, 3), (6, 6), (11, 11)]


def test_a_function_without_a_body_is_not_a_unit():
    source = """\
interface Shape {
    fun area(): Int
}

abstract class Base {
    abstract fun name(): String
}

fun kept() = 1
"""
    assert spans(source) == [(9, 9)]


def test_a_secondary_constructor_with_a_body_is_a_unit():
    source = """\
class Box(val a: Int) {
    constructor(a: String) : this(a.length) {
        println(a)
    }
}
"""
    assert spans(source) == [(2, 4)]


def test_a_constructor_that_only_delegates_is_not_a_unit():
    source = """\
class Box(val a: Int) {
    constructor() : this(0)
    constructor(a: String) : this(a.length)
    fun kept() = 1
}
"""
    assert spans(source) == [(4, 4)]


def test_getters_and_setters_with_a_body_are_units():
    source = """\
class Box {
    var size: Int = 0
        get() = field
        set(value) {
            field = value
        }
    val plain: Int = 1
}
"""
    assert spans(source) == [(3, 3), (4, 6)]


def test_functions_nested_in_a_unit_are_not_their_own_units():
    source = """\
fun outer(xs: List<Int>): Int {
    fun local(p: Int) = p + 1
    val job = object : Runnable {
        override fun run() { local(1) }
    }
    val anon = fun(a: Int): Int { return a }
    xs.forEach { x ->
        println(x)
    }
    return xs.size
}
"""
    assert spans(source) == [(1, 11)]


def test_members_of_an_object_declared_inside_a_class_are_units():
    source = """\
class Box {
    companion object {
        fun make() = Box()
    }
}
"""
    assert spans(source) == [(3, 3)]


def test_a_getter_inside_a_property_initialised_by_a_lambda_is_not_a_unit():
    source = """\
val handler = Handler { value: Int ->
    object : Holder {
        val size: Int get() = value
    }
}

fun kept() = 1
"""
    assert spans(source) == [(7, 7)]
