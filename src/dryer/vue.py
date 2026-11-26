"""Extract script blocks and candidate functions from Vue Single File Components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from dryer.treesitter import child_of_type, node_text, parse, parse_range

ScriptGrammar = Literal["javascript", "typescript", "tsx"]


@dataclass(frozen=True)
class ScriptBlock:
    grammar: ScriptGrammar
    is_setup: bool
    span: object


_SCRIPT_GRAMMARS: dict[str, ScriptGrammar] = {
    "": "javascript",
    "js": "javascript",
    "jsx": "javascript",
    "mjs": "javascript",
    "cjs": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "mts": "typescript",
    "cts": "typescript",
    "typescript": "typescript",
    "tsx": "tsx",
}

_TS_FUNCTION = {
    "function_declaration",
    "method_definition",
    "arrow_function",
    "function_expression",
}
_WRAPPERS = {"parenthesized_expression", "as_expression", "satisfies_expression"}
_SKIP_OPTION_KEYS = {"props", "emits", "components", "directives", "provide", "inject"}
_EFFECT_HOOKS = {
    "watchEffect",
    "watchPostEffect",
    "watchSyncEffect",
    "onBeforeMount",
    "onMounted",
    "onBeforeUpdate",
    "onUpdated",
    "onBeforeUnmount",
    "onUnmounted",
    "onActivated",
    "onDeactivated",
    "onErrorCaptured",
    "onRenderTracked",
    "onRenderTriggered",
    "onServerPrefetch",
}


def _attr_value(data: bytes, attr) -> str:
    quoted = child_of_type(attr, "quoted_attribute_value")
    node = (
        child_of_type(quoted, "attribute_value")
        if quoted is not None
        else child_of_type(attr, "attribute_value")
    )
    return node_text(data, node) if node is not None else ""


def _tag_attrs(data: bytes, start_tag) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for child in start_tag.children:
        if child.type != "attribute":
            continue
        name_node = child_of_type(child, "attribute_name")
        if name_node is not None:
            attrs[node_text(data, name_node).lower()] = _attr_value(data, child)
    return attrs


def _script_block(data: bytes, element) -> ScriptBlock | None:
    start_tag = child_of_type(element, "start_tag")
    if start_tag is None:
        return None
    attrs = _tag_attrs(data, start_tag)
    if "src" in attrs:
        return None
    grammar = _SCRIPT_GRAMMARS.get(attrs.get("lang", "").strip().lower())
    raw_text = child_of_type(element, "raw_text")
    if grammar is None or raw_text is None or not node_text(data, raw_text).strip():
        return None
    return ScriptBlock(grammar=grammar, is_setup="setup" in attrs, span=raw_text.range)


def extract_script_blocks(source: str) -> tuple[bytes, list[ScriptBlock]]:
    data, tree = parse(source, "vue")
    blocks: list[ScriptBlock] = []
    for child in tree.root_node.children:
        if child.type == "script_element":
            block = _script_block(data, child)
            if block is not None:
                blocks.append(block)
    return data, blocks


def _named_children(node) -> list:
    return [child for child in node.named_children if child.type != "comment"]


def _unwrap(node):
    while node is not None and node.type in _WRAPPERS:
        children = _named_children(node)
        if not children:
            return None
        node = children[0]
    return node


def _is_fn_expr(node) -> bool:
    if node is None:
        return False
    if node.type == "arrow_function":
        return node.child_by_field_name("body") is not None
    return node.type == "function_expression" and child_of_type(node, "statement_block") is not None


def _pair_key(data: bytes, pair) -> str | None:
    key = pair.child_by_field_name("key")
    if key is None:
        return None
    if key.type in {"property_identifier", "identifier"}:
        return node_text(data, key)
    if key.type == "string":
        fragment = child_of_type(key, "string_fragment")
        return node_text(data, fragment) if fragment is not None else ""
    return None


def _object_pairs(data: bytes, obj) -> list[tuple[str, object]]:
    pairs: list[tuple[str, object]] = []
    for child in obj.children:
        if child.type != "pair":
            continue
        key = _pair_key(data, child)
        val = _unwrap(child.child_by_field_name("value"))
        if key is not None and val is not None:
            pairs.append((key, val))
    return pairs


def _pair_fns(data: bytes, obj, keys: set[str] | None = None) -> list:
    found = []
    for key, val in _object_pairs(data, obj):
        if keys is not None and key not in keys:
            continue
        if _is_fn_expr(val):
            found.append(val)
    return found


def _computed_option_fns(data: bytes, obj) -> list:
    found = []
    for _key, val in _object_pairs(data, obj):
        if _is_fn_expr(val):
            found.append(val)
        elif val.type == "object":
            found.extend(_pair_fns(data, val, {"get", "set"}))
    return found


def _watch_entry_fns(data: bytes, val) -> list:
    if _is_fn_expr(val):
        return [val]
    if val.type == "object":
        return _pair_fns(data, val, {"handler"})
    return []


def _watch_option_fns(data: bytes, obj) -> list:
    found = []
    for _key, val in _object_pairs(data, obj):
        if val.type == "array":
            for item in _named_children(val):
                found.extend(_watch_entry_fns(data, _unwrap(item)))
        else:
            found.extend(_watch_entry_fns(data, val))
    return found


_OPTION_SECTIONS = {
    "methods": _pair_fns,
    "computed": _computed_option_fns,
    "watch": _watch_option_fns,
}


def _collect_options(data: bytes, obj) -> list:
    found = []
    for key, val in _object_pairs(data, obj):
        if key in _SKIP_OPTION_KEYS:
            continue
        section = _OPTION_SECTIONS.get(key) if val.type == "object" else None
        if section is not None:
            found.extend(section(data, val))
        elif _is_fn_expr(val):
            found.append(val)
    return found


def _callee_name(data: bytes, callee) -> tuple[str | None, str] | None:
    target = _unwrap(callee)
    if target is None:
        return None
    if target.type == "identifier":
        return None, node_text(data, target)
    if target.type == "member_expression":
        obj = _unwrap(target.child_by_field_name("object"))
        prop = target.child_by_field_name("property")
        if obj is not None and prop is not None and obj.type == "identifier":
            return node_text(data, obj), node_text(data, prop)
    return None


_VUE_RECEIVERS = frozenset({None, "Vue", "vue"})
_COMPONENT_CALLS = frozenset(
    {
        (None, "defineComponent"),
        ("Vue", "defineComponent"),
        ("vue", "defineComponent"),
        ("Vue", "extend"),
        ("vue", "extend"),
    }
)


def _fn_or_object(data: bytes, node, on_object) -> list:
    if node is None:
        return []
    if node.type == "object":
        return on_object(data, node)
    return [node] if _is_fn_expr(node) else []


def _computed_object(data: bytes, obj) -> list:
    return _pair_fns(data, obj, {"get", "set"})


def _arg(args: list, index: int):
    return _unwrap(args[index]) if index < len(args) else None


def _fn_arg(args: list, index: int) -> list:
    arg = _arg(args, index)
    return [arg] if _is_fn_expr(arg) else []


def _composition_call_nodes(
    data: bytes, resolved: tuple[str | None, str], args: list
) -> list:
    receiver, name = resolved
    if receiver not in _VUE_RECEIVERS:
        return []
    if name == "computed":
        return _fn_or_object(data, _arg(args, 0), _computed_object)
    if name == "watch":
        return _fn_arg(args, 1)
    if name in _EFFECT_HOOKS:
        return _fn_arg(args, 0)
    return []


def _call_nodes(data: bytes, call) -> list:
    resolved = _callee_name(data, call.child_by_field_name("function"))
    args_node = call.child_by_field_name("arguments")
    if resolved is None or args_node is None:
        return []
    args = _named_children(args_node)
    if resolved in _COMPONENT_CALLS:
        return _fn_or_object(data, _arg(args, 0), _collect_options)
    return _composition_call_nodes(data, resolved, args)


def _export_default_nodes(data: bytes, node) -> list:
    if not any(child.type == "default" for child in node.children):
        return []
    value = _unwrap(node.child_by_field_name("value"))
    return _fn_or_object(data, value, _collect_options)


def _vue_extra_nodes(data: bytes, root) -> list:
    found = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _TS_FUNCTION:
            continue
        if node.type == "export_statement":
            found.extend(_export_default_nodes(data, node))
        elif node.type == "call_expression":
            found.extend(_call_nodes(data, node))
        stack.extend(reversed(node.children))
    return found


def _unique_sorted(nodes: list) -> list:
    seen: set[tuple[int, int]] = set()
    unique = []
    for node in sorted(nodes, key=lambda item: (item.start_byte, item.end_byte)):
        span = (node.start_byte, node.end_byte)
        if span not in seen:
            seen.add(span)
            unique.append(node)
    return unique


def extract_vue_nodes(
    source: str, pick_base: Callable[[bytes, object], list]
) -> tuple[bytes, list]:
    data, blocks = extract_script_blocks(source)
    found: list = []
    for block in blocks:
        tree = parse_range(data, block.grammar, block.span)
        found.extend(pick_base(data, tree.root_node))
        found.extend(_vue_extra_nodes(data, tree.root_node))
    return data, _unique_sorted(found)
