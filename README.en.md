# Taiyi Shuji

[中文](README.md) · [MIT License](LICENSE)

A personal Traditional Chinese Medicine analysis Skill, currently designed and
validated primarily for Codex.

Taiyi Shuji keeps classical interpretation, formula analysis, case reasoning,
same-case follow-up, and a lightweight personal case record on one verifiable
mainline. Model knowledge and TCM reasoning remain primary. The bundled digital
classics knowledge base verifies direct quotations, attribution, source
authority, counterevidence, and decisive boundaries. No separate model API is
required.

> This project is for research and personal study of TCM classics and formulas.
> It is not a medical device and does not provide a diagnosis or prescription
> that can be acted on without professional review. The images below demonstrate
> report presentation only; they do not establish medical validity.

## What it does

| Capability | Description |
|---|---|
| Classical interpretation | Explains passages, concepts, and cross-text relationships; direct classical claims can be bound to a short quotation and document anchor |
| Formula analysis | Supports named or unnamed formulas, one or many ingredients, same-formula continuation, and comparison; conclusions remain conditional without patient facts |
| Case reasoning | Preserves the patient's exact words and current facts, then performs foundational analysis, medical translation, pattern differentiation, and formula reasoning within the TCM system |
| Same-case follow-up | Binds an explicit parent turn, compares earlier predictions with current observations, and reassesses whether to continue, adjust, change, or start again |
| Personal case record | Stores facts, ambiguities, prior clinician opinions, actual formulas, observed responses, corrections, and committed result identities without building a full medical-record system |
| Same-source presentation | Complete text is the default; a read-only mobile H5 or pure-image report can be generated from the same committed result on explicit request |

## Quick start

### Requirements

- Codex, the only Agent host currently covered by installation and runtime acceptance;
- one isolated native subagent for red-team review of formula, case, and follow-up tasks;
- Python 3.10 or later;
- macOS or Linux. WSL is recommended on Windows, which has not been separately tested;
- Codex image generation, localized editing, and original-image inspection for pure-image reports.

Other Agent hosts may expose similar Skill, file, terminal, or subagent features,
but they have not been compatibility-tested. A host that cannot create the
isolated subagent must not claim that formal red-team review was completed.

### Install

```bash
git clone https://github.com/gethlx/taiyi.git
cd taiyi

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

For Codex, use a symbolic link so the Skill retains its relative access to
`spec/`, `tools/`, and `kb/`:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skill/taiyi-shuji" ~/.codex/skills/taiyi-shuji
```

If a Skill with the same name already exists, decide whether to keep, rename,
or update it instead of overwriting it blindly. Start a new Codex task after an
installation or update so the host reloads the Skill.

### Use it in a conversation

Invoke `$taiyi-shuji` explicitly and provide only the facts needed for the
current task. For example:

```text
Use $taiyi-shuji to explain how “one yin and one yang are called the Way” in the Yijing relates to the Cantong qi.
```

```text
Use $taiyi-shuji to analyze this unnamed formula: Yinchen, Patrinia, Sedum sarmentosum, Gardenia...
There are no patient facts. Keep the formula meaning, pattern conditions, and Day 1/2/3 observations conditional.
```

```text
Use $taiyi-shuji to record the facts of this case and perform TCM reasoning. The patient's exact words are: ...
```

```text
Use $taiyi-shuji to follow up on the currently active case. The changes since the previous treatment are: ...
```

Recording, reading, or correcting case facts does not start the full medical
mainline. A plain explanation of an existing result does not create a new run,
turn, or result. Hypothetical formula changes use a copy-on-write sandbox and do
not modify the formal case. H5 and pure-image reports are generated only after
the text result is complete and the user explicitly requests them.

## How it works

Formal tasks use three causal responsibilities:

1. **R0** establishes qi, yin-yang, relevant *Yijing* relationships, and any
   necessary five-phase direction without prematurely assigning organs,
   channels, patterns, or treatment.
2. **R1** translates R0 into human qi transformation, the six channels and eight
   principles, organs and channels, disease movement, and formula-pattern
   relationships. Competing explanations are checked before retaining a core
   mechanism.
3. **R2** develops treatment principles, whole-formula structure, conditional
   recommendations, Day 1/2/3 observations, and exit boundaries.

The host completes R0–R2 sequentially in one context. The classics service
supplies only the short passages needed for the current reasoning; it does not
inject chapters or whole works. Formula, case, and follow-up tasks then call one
isolated red-team context that does not inherit the host conversation. If it
finds a material conflict, the host performs one synthesis rather than running
a fixed multi-agent pipeline or vote.

Each formal result is committed once and binds the current input, selected
sources, role outputs, and result identity. Failure cannot leave a partial
medical result. H5 and image reports read that same committed result and do not
store a second medical state.

## Output examples

The four pages below show qi-transformation direction, conditional pattern
reasoning, a case mechanism, and formula structure. They are visual projections
of the committed text analysis, not a separate interpretation layer.

<table>
  <tr>
    <td width="50%" align="center">
      <img src="docs/images/qi-transformation-r0.png" alt="Taiyi Shuji R0 qi-transformation analysis"><br>
      <strong>R0 · Qi transformation</strong><br>Circulation, opening-closing-pivoting, and five-phase direction
    </td>
    <td width="50%" align="center">
      <img src="docs/images/conditional-pattern-r1.png" alt="Taiyi Shuji R1 conditional pattern analysis"><br>
      <strong>R1 · Conditional pattern mechanism</strong><br>Human qi transformation, disease movement, and differentiation boundaries
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/images/case-pattern-mechanism.png" alt="Taiyi Shuji case cause, mechanism, and pattern differentiation"><br>
      <strong>Case · Cause, mechanism, and pattern</strong><br>A mechanism chain grounded in current facts, with unresolved boundaries retained
    </td>
    <td width="50%" align="center">
      <img src="docs/images/formula-groups.png" alt="Taiyi Shuji formula structure analysis"><br>
      <strong>R2 · Formula structure</strong><br>Treatment direction and functional group relationships
    </td>
  </tr>
</table>

## Digital classics and validation

The repository includes the processed knowledge base used by the Skill:

- `kb/manifest.json`: stable identities, runtime paths, and SHA-256 digests for 18 works;
- `kb/texts/`: the single runtime copy of each work after work separation, encoding normalization, structural headings, and stable anchors were added;
- `kb/assets/辅行诀/`: the Tangye diagram, Jingfa rules, and their structured validation assets.

Raw download snapshots and historical merged source files are not runtime corpus
copies. Formal use stops if the manifest, a declared text, or a structured asset
is missing, replaced, or fails its digest check. See [`kb/README.md`](kb/README.md)
and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for structure, provenance,
and licensing details.

Run the complete validation suite:

```bash
python3 -B tools/validate.py
```

The knowledge-base checks can also be run separately:

```bash
python3 -B tools/retrieval.py validate
python3 -B tools/test_retrieval.py
python3 -B tools/tangye.py validate
```

Machine tests cover deterministic identity, conservation, provenance, role
isolation, and atomic commit boundaries. They do not judge yin-yang analysis,
mechanism, formula meaning, materia medica, treatment quality, or red-team
medical quality.

## Project documents and license

- [Product boundaries](PRODUCT.md)
- [Theory core and responsibilities](THEORY_CORE.md)
- [Implementation architecture](ARCHITECTURE.md)
- [Machine contract](spec/MACHINE_CONTRACT.md)
- [Evidence service](spec/RETRIEVAL.md)

Software, original documentation, and repository example images are available
under the [MIT License](LICENSE). Bundled third-party digital classics retain
their source and license identities and are not relicensed by the software
license.
