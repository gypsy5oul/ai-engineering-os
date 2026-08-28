---
name: ai-evaluation
description: Measure whether the AI system this project is building actually works - datasets, baselines, candidates, metrics and regression. Use when an AI behaviour is specified, changed or reviewed. This is about the product; evaluating this organization's own agents is agent-evaluation.
---

# AI evaluation

An AI component's correctness is a **rate on a dataset**, not a property a test
asserts. A change to it is a change to that rate, and a change nobody measured is
a change nobody can defend.

**Not to be confused with `agent-evaluation`.** That one evaluates this
organization's own roles — whether `security-reviewer` stays inside its
authority. This one evaluates the software the organization is building. Same
discipline, different subject, and mixing them produces a suite that measures
neither.

## The dataset comes first

Not the prompt. Not the model. The dataset, because until it exists there is no
statement of what "working" means that anyone can check.

- **Build it from real inputs.** Invented examples encode what you expect, and
  what you expect is precisely the thing that is not failing.
- **Include the cases you know are hard**: the ambiguous ones, the ones where the
  right answer is "I cannot tell", the ones that look like a different category.
  A dataset of easy cases reports a high number and predicts nothing.
- **Every case has an expected outcome somebody stands behind.** Where the
  expected outcome is a judgement, record whose.
- **Hold some out.** A dataset you tuned the prompt against measures how well you
  tuned, not how well it works.
- **It is an artifact.** Versioned, reviewed, in the repository, and changed
  deliberately: a dataset edited to make a run pass is the same defect as a test
  edited to make a build pass.
- **The project says where it lives**, in `.ai-engineering/project.yaml` under
  `ai_system.evaluation`, alongside the baseline it is compared against. A
  dataset nobody can find from the configuration is a dataset one person knows
  about.

## Baseline and candidate

Every meaningful AI evaluation is a **comparison**, not a threshold.

```
baseline    the current production behaviour: prompt version,
            model version, retrieval index version, dataset version
candidate   the proposed change, on the same dataset
```

An absolute number ("87% correct") answers almost nothing on its own. The
questions that decide a release are comparative:

- Did the thing being fixed get better?
- **Did anything else get worse?** This is the one that catches people. A prompt
  change that fixes a category usually moves another, and the regression is
  invisible unless the whole dataset runs.
- Is the difference bigger than the noise? Two runs of the *same* configuration
  differ. Run the baseline twice before believing a small delta.

**Change one variable at a time.** A prompt change and a model upgrade shipped
together produce a number nobody can attribute. See `prompt-engineering`.

## Metrics

Pick metrics for what the system decides. Do not report a metric you cannot act
on.

| Dimension | The question |
| --- | --- |
| Correctness / task success | Did it do the thing? |
| Groundedness | Did the answer come from the provided context, or from the model? |
| Retrieval quality | Was the right context available at all? Measure before answer quality — see `rag-engineering` |
| Tool-call correctness | Right tool, right arguments, right order? |
| Refusal behaviour | Does it refuse what it should, and *only* what it should? Over-refusal is a failure |
| Latency, cost | Per call and per completed task, not per token |
| Robustness | Paraphrase, typos, adversarial input, injected instructions |

**Fabricated metrics are worse than no metrics.** A number nobody can reproduce
from the dataset and the configuration is not evidence, and reporting one is the
failure this whole discipline exists to prevent.

## Deterministic and model-judged, kept apart

Two kinds, and merging them is how a suite stops meaning anything:

- **Deterministic** — exact match, schema validity, a rule, a retrieval hit.
  Cheap, reproducible, runs on every change. Anything that *can* be deterministic
  should be.
- **Model-judged** — a rubric applied by a model where correctness is a
  judgement. Real signal, and it has a measurement error of its own: judges are
  biased toward longer answers, toward their own outputs, and by option order.

Rules that keep the second honest, and which this repository applies to its own
suite in `${CLAUDE_PLUGIN_ROOT}/policies/evaluation-policy.json`:

- **Never auto-pass a judged case.** Pending is a result; assumed is not.
- **Never let a judged case be the only gate on something safety-critical.** Back
  it with a deterministic one.
- **Validate the judge** against human labels on a sample before trusting it.
- **Never judge with the model under test**, on its own output.

## Regression

A defect that escaped once becomes a permanent case. That is the whole mechanism:
the dataset grows by the failures found in production, so the same failure cannot
ship twice.

Set thresholds as **gates on the comparison**, not on the absolute: "no category
drops by more than *x* against baseline" survives a dataset getting harder;
"correctness above 90%" does not.

## Rules

- The dataset exists before the prompt. Otherwise "working" is undefined.
- Every result names the four versions: prompt, model, index, dataset.
- Baseline and candidate on the same dataset, one variable changed.
- A regression anywhere is a finding, even when the target metric improved.
- Never report a metric that was not produced by a run somebody can repeat.
