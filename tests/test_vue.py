from pathlib import Path

from dryer.cli import run
from dryer.extract import entries_in_source
from dryer.model import Entry
from dryer.scan import find_duplicates, scan_files
from dryer.vue import extract_script_blocks


def write_source(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def vue_entries(source: str, file: str = "Card.vue") -> list[Entry]:
    entries, warning = entries_in_source("vue", source, file, file)
    assert warning is None
    return entries


def vue_spans(source: str, file: str = "Card.vue") -> list[tuple[int, int]]:
    return [(entry.start_line, entry.end_line) for entry in vue_entries(source, file)]


def scan_score(tmp_path: Path, files: dict[str, str]) -> float:
    for name, source in files.items():
        write_source(tmp_path, name, source)
    paths = sorted(tmp_path / name for name in files)
    entries, warnings = scan_files(paths, tmp_path, min_lines=1, min_nodes=1)
    assert warnings == []
    found = find_duplicates(entries, threshold=0.0)
    assert len(found) == 1
    return found[0].score


def test_vue_to_vue_duplicate_detection(tmp_path):
    left = """\
<template><div>{{ title }}</div></template>
<script setup lang="ts">
function loadItems(xs: number[]): number[] {
  const ys = filter(xs, odd)
  return map(ys, inc)
}
</script>
"""
    right = """\
<template><span>{{ heading }}</span></template>
<script setup lang="ts">
function fetchRows(items: number[]): number[] {
  const kept = filter(items, even)
  return map(kept, dec)
}
</script>
"""
    different = """\
<template><span>{{ heading }}</span></template>
<script setup lang="ts">
function fetchRows(items: number[]): number[] {
  const kept = select(items, even)
  return collect(kept, dec)
}
</script>
"""
    assert scan_score(tmp_path, {"Left.vue": left, "Right.vue": right}) == 1.0
    assert scan_score(tmp_path, {"Left.vue": left, "Diff.vue": different}) < 1.0


def test_vue_cross_file_comparison_with_ts_and_tsx(tmp_path):
    vue_setup = """\
<template><div /></template>
<script setup lang="ts">
const computeTotal = (xs: number[]): number[] => {
  const ys = filter(xs, odd)
  return map(ys, inc)
}

const doubled = computed<number>(() => {
  const items = loadRows(query)
  return items.filter((item) => item.active)
})

const side = Vue.computed(() => {
  const rows = fetchData(key)
  return rows.map((row) => row.value)
})

watch(
  () => source.value,
  (val: unknown) => {
    const next = normalizeValue(val)
    commitState(next)
  }
)

onMounted(() => {
  const initial = loadInitial(config)
  applyState(initial)
})
</script>
"""
    ts_match = """\
export const computeSum = (items: number[]): number[] => {
  const kept = filter(items, even)
  return map(kept, dec)
}

export const doubledCopy = () => {
  const entries = loadRows(filterKey)
  return entries.filter((entry) => entry.enabled)
}

export const sideCopy = () => {
  const list = fetchData(token)
  return list.map((el) => el.amount)
}

export const watchCopy = (nextVal: unknown) => {
  const cleaned = normalizeValue(nextVal)
  commitState(cleaned)
}

export const mountCopy = () => {
  const seed = loadInitial(opts)
  applyState(seed)
}
"""
    write_source(tmp_path, "Panel.vue", vue_setup)
    write_source(tmp_path, "helpers.ts", ts_match)
    entries, warnings = scan_files(
        [tmp_path / "Panel.vue", tmp_path / "helpers.ts"],
        tmp_path,
        min_lines=3,
        min_nodes=1,
    )
    assert warnings == []
    assert all(entry.language == "typescript" for entry in entries)
    found = find_duplicates(entries, threshold=0.95)
    pairs = {(item.left.file, item.right.file, item.left.start_line, item.right.start_line) for item in found}
    assert ("Panel.vue", "helpers.ts", 3, 1) in pairs
    assert ("Panel.vue", "helpers.ts", 8, 6) in pairs
    assert ("Panel.vue", "helpers.ts", 13, 11) in pairs
    assert ("Panel.vue", "helpers.ts", 20, 16) in pairs
    assert ("Panel.vue", "helpers.ts", 26, 21) in pairs

    vue_tsx = """\
<script lang="tsx">
export const Card = (props: Props) => {
  return <div className={props.cls}><span>{format(props.name)}</span></div>
}
</script>
"""
    tsx_file = """\
export const Badge = (item: Opts) => {
  return <div className={item.kind}><span>{format(item.title)}</span></div>
}
"""
    sub = tmp_path / "tsx_case"
    assert scan_score(sub, {"Card.vue": vue_tsx, "Badge.tsx": tsx_file}) == 1.0


def test_options_api_methods_and_pair_functions_match_ts(tmp_path):
    vue_options = """\
<script lang="ts">
export default defineComponent({
  data: () => ({
    rows: filterRows(seed, active),
    total: sumRows(seed),
  }),
  mounted() {
    const items = fetchItems(endpoint)
    return renderItems(items)
  },
  unmounted: function () {
    const subs = readSubs(registry)
    return clearSubs(subs)
  },
  methods: {
    save() {
      const valid = validateOrder(draft)
      return submitOrder(valid)
    },
    load: (id: string) => {
      const raw = fetchRecord(id)
      const clean = sanitizeRecord(raw)
      return formatRecord(clean)
    },
  },
  computed: {
    summary() {
      return summarize(rows)
    },
    fullName: {
      get: () => joinNames(first, last),
      set: (val: string) => {
        const parts = splitName(val)
        updateParts(parts)
      },
    },
  },
  watch: {
    count(next: number) {
      refreshCount(next)
    },
    query: {
      handler: (term: string) => {
        const hits = searchIndex(term)
        publishHits(hits)
      },
      immediate: true,
    },
    items: [
      (list: Item[]) => {
        const sorted = sortItems(list)
        syncItems(sorted)
      },
      {
        handler: function (list: Item[]) {
          const grouped = groupItems(list)
          cacheGroups(grouped)
        },
      },
    ],
  },
})
</script>
"""
    ts_standalone = """\
export const loadStandalone = (key: string) => {
  const raw = fetchRecord(key)
  const clean = sanitizeRecord(raw)
  return formatRecord(clean)
}

export function clearStandalone() {
  const subs = readSubs(store)
  return clearSubs(subs)
}
"""
    assert vue_spans(vue_options) == [
        (3, 6),
        (7, 10),
        (11, 14),
        (16, 19),
        (20, 24),
        (27, 29),
        (31, 31),
        (32, 35),
        (39, 41),
        (43, 46),
        (50, 53),
        (55, 58),
    ]

    write_source(tmp_path, "Opt.vue", vue_options)
    write_source(tmp_path, "standalone.ts", ts_standalone)
    entries, warnings = scan_files(
        [tmp_path / "Opt.vue", tmp_path / "standalone.ts"],
        tmp_path,
        min_lines=3,
        min_nodes=1,
    )
    assert warnings == []
    found = find_duplicates(entries, threshold=0.82)
    cross = [
        (item.left.start_line, item.right.start_line, item.score)
        for item in found
        if item.left.file != item.right.file
    ]
    assert any(left == 20 and right == 1 and score >= 0.82 for left, right, score in cross)
    assert any(left == 11 and right == 7 and score >= 0.82 for left, right, score in cross)


def test_options_api_variants_and_functional_components():
    vue_extend = """\
<script lang="ts">
export default Vue.extend({
  methods: {
    run: () => {
      return 1
    },
  },
})
</script>
"""
    const_component = """\
<script lang="ts">
const Widget = defineComponent({
  methods: {
    run: () => {
      return 1
    },
  },
})
</script>
"""
    functional_define = """\
<script lang="ts">
export default defineComponent((props: Props) => {
  return () => h('div', props.label)
})
</script>
"""
    anon_arrow = """\
<script lang="ts">
export default ((props: Props) => h('div', props.label)) as Component
</script>
"""
    anon_fn = """\
<script lang="ts">
export default function () {
  return h('div')
}
</script>
"""
    assert vue_spans(vue_extend) == [(4, 6)]
    assert vue_spans(const_component) == [(4, 6)]
    assert vue_spans(functional_define) == [(2, 4)]
    assert vue_spans(anon_arrow) == [(2, 2)]
    assert vue_spans(anon_fn) == [(2, 4)]


def test_dual_script_blocks_preserve_order_with_no_duplicate_spans():
    source = """\
<script lang="ts">
export function helper(x: number) {
  return x + 1
}
</script>

<script setup lang="ts">
const doubled = computed(() => {
  return helper(1)
})

function reset() {
  return 0
}
</script>
"""
    spans = vue_spans(source)
    assert spans == [(2, 4), (8, 10), (12, 14)]
    assert len(spans) == len(set(spans))


def test_nested_callbacks_getters_and_non_function_options_are_skipped():
    source = """\
<script lang="ts">
export default defineComponent({
  props: {
    items: {
      default: () => [],
    },
  },
  emits: {
    change: (id: number) => id > 0,
  },
  provide: {
    helper: () => 1,
  },
  setup() {
    const doubled = computed(() => count.value * 2)
    onMounted(() => log(doubled.value))
    return { doubled }
  },
})

const ratio = computed({
  get: () => base.value * 2,
  set: (v: number) => {
    base.value = v / 2
  },
})

watch(
  () => [state.a, state.b],
  ([a, b]) => {
    syncPair(a, b)
  }
)

const mapped = items.map((item) => item + 1)
fs.watch('./x', () => reload())
_.extend({}, { run: () => 1 })
</script>
"""
    assert vue_spans(source) == [(14, 18), (22, 22), (23, 25), (30, 32)]


def test_vue_script_block_edge_cases():
    assert vue_entries("<template><div>hi</div></template>\n") == []
    assert vue_entries("<script>   \n  </script>\n") == []
    assert vue_entries('<script src="./ext.ts">const x = () => 1</script>\n') == []
    assert vue_entries('<script lang="coffee">x = -> 1</script>\n') == []

    ignored = """\
<!-- <script>function hidden() { return 1 }</script> -->
<template><div><script>function inTemplate() { return 1 }</script></div></template>
<script setup lang="TS" generic="T extends Record<string, unknown>">
function real(x: T): T {
  return x
}
</script>
<script lang="jsx">
export function Card(props) {
  return <div>{props.name}</div>
}
</script>
"""
    data, blocks = extract_script_blocks(ignored)
    assert data
    assert [(block.grammar, block.is_setup) for block in blocks] == [
        ("typescript", True),
        ("javascript", False),
    ]
    assert vue_spans(ignored) == [(4, 6), (9, 11)]


def test_bom_crlf_multibyte_and_inline_script_line_numbers():
    source = (
        "\ufeff<template><p>你好 世界 🚀</p></template>\r\n"
        '<script setup lang="ts">const greet = (name: string) => {\r\n'
        '  const msg = "测试 🎉"\r\n'
        "  return formatText(msg, name)\r\n"
        "}</script>\r\n"
        "<script>export default { data: () => ({ label: '中文' }) }</script>\r\n"
    )
    assert vue_spans(source) == [(2, 5), (6, 6)]


def test_template_string_interpolation_stays_in_structure(tmp_path):
    plain = "<script setup lang=\"ts\">\nconst f = (x: string) => {\n  return `Hello`\n}\n</script>\n"
    interp_a = "<script setup lang=\"ts\">\nconst f = (user: User) => {\n  return `Hello ${user.name}`\n}\n</script>\n"
    interp_b = "<script setup lang=\"ts\">\nconst g = (row: Row) => {\n  return `Hi ${row.title}`\n}\n</script>\n"
    assert scan_score(tmp_path / "same", {"A.vue": interp_a, "B.vue": interp_b}) == 1.0
    assert scan_score(tmp_path / "diff", {"A.vue": interp_a, "B.vue": plain}) < 1.0


def test_cli_end_to_end_with_vue_files(tmp_path, capsys):
    left = """\
<template><div>{{ name }}</div></template>
<script setup lang="ts">
function processOrder(xs: number[]): number[] {
  const ys = filter(xs, odd)
  return map(ys, inc)
}
</script>
"""
    right = """\
<template><div>{{ title }}</div></template>
<script setup lang="ts">
function handleInvoice(items: number[]): number[] {
  const kept = filter(items, even)
  return map(kept, dec)
}
</script>
"""
    write_source(tmp_path, "src/Order.vue", left)
    write_source(tmp_path, "src/Invoice.vue", right)
    write_source(tmp_path, "src/Order.test.vue", left)
    write_source(tmp_path, "src/Invoice.spec.vue", right)

    code = run(["--root", str(tmp_path), "--min-lines", "3", "--min-nodes", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert "DUPLICATE score=1.00" in out
    assert "src/Order.vue:3-6" in out
    assert "src/Invoice.vue:3-6" in out
    assert "Order.test.vue" not in out
    assert "Invoice.spec.vue" not in out

    edn = (tmp_path / ".metrics" / "dry.edn").read_text(encoding="utf-8")
    assert ':language "typescript"' in edn
    assert ':file "src/Order.vue"' in edn
    assert ':file "src/Invoice.vue"' in edn


def test_vue_edge_keys_and_non_vue_callees():
    source = """\
<script lang="ts">
const dynKey = "dynamic";
export default defineComponent({
  [dynKey]: () => 1,
  computed: {
    flat: () => count.value + 1,
    raw: 42,
  },
  watch: {
    "user.name": {
      handler: (next: string) => syncName(next),
    },
    "": {
      handler: () => resetEmpty(),
    },
    tag: "onTagChange",
    bad: 123,
  },
});

export default existingComponent;
defineComponent();
const c1 = computed(existingFn);
const c2 = computed({ get: () => 1, other: () => 2 });
watch(onlySource);
getFactory()(() => 1);
app.vue.watch(x, () => 2);
otherCall(() => 3);
</script>
"""
    assert vue_spans(source) == [(6, 6), (11, 11), (14, 14), (24, 24)]

