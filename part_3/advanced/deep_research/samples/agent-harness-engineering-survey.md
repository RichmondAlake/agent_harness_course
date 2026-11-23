# Agent Harness Engineering: A Survey of the Scaffolding, Control Loops, and Runtime Infrastructure Around LLM Agents

**Abstract.** Large language model agents are deployed inside a harness: the software layer that assembles prompts and tool schemas, dispatches actions, manages the context window, verifies outputs, enforces permissions and records traces. This survey treats the harness as an engineering object in its own right. It adopts the view that agent behaviour is jointly produced by a stochastic model policy and the harness that constructs its context, defines its actions and acts on its outputs. We propose a six-layer framework (control loop, action interface, context, memory, execution environment and orchestration) with three cross-cutting concerns: security, evaluation and automated design. Across these themes we compare design choices and their empirical support, including reasoning–acting loops, reflection and tree search, code versus structured tool calls, summarisation versus deterministic eviction, sandbox isolation and multi-agent coordination. Controlled studies show that changing only the harness can shift Pass@1 by up to 27.4 points for a fixed model, a spread comparable to differences between models, although the size of the effect depends on task, model and budget. We also highlight cross-layer interactions, such as context compaction silently erasing governance constraints and protocols like MCP amplifying prompt-injection risk. We close with methodological recommendations for disclosing harnesses, reporting cost alongside accuracy and auditing benchmark validity, and with open problems in making harnesses reproducible.

**Keywords:** agent harness, LLM agents, context engineering, tool interfaces, agent evaluation

## Contents

1. Introduction
2. Background and Definitions
3. A Framework for Harness Components
4. Control Loops and Planning Scaffolds
5. Tool and Action Interfaces
6. Context Engineering and Memory
7. Execution Environments and Sandboxing
8. Orchestration and Multi-Agent Harnesses
9. Safety, Observability, and Cost Control
10. Evaluation and Evidence
11. Open Problems and Future Directions
12. Conclusion

## 1. Introduction

Large language model (LLM) agents are rarely deployed as bare models. Between the weights and the task sits a layer of software. It assembles prompts and tool schemas, dispatches actions, decides what stays in the context window, checks outputs, enforces permissions and records traces. Practitioners and researchers increasingly call this layer the *harness*. It is also increasingly treated as an object of engineering in its own right rather than incidental glue code. This survey reviews the scaffolding, control loops and runtime infrastructure that make up agent harnesses. It asks what is known about how they shape agent behaviour.

### Why the harness deserves first-class treatment

The early agent literature already located much of an agent's competence outside the model. ReAct recast an agent as a policy whose action space is augmented with language "thoughts" that update context without touching the environment. Interleaving these thoughts with tool calls to a simple Wikipedia API outperformed reasoning-only and acting-only prompting on knowledge-intensive and interactive tasks [1]. Reflexion kept model weights fixed and improved agents across trials by storing verbal self-reflections in an episodic memory that conditions later attempts [2]. That is a gain produced entirely by what the surrounding system feeds back into context. SWE-agent made the point sharper: it argued that LM agents are a new category of end user and showed that a purpose-built agent–computer interface substantially changes how well an agent edits code, navigates repositories and runs tests [3].

More recent controlled studies try to measure the effect directly. Claw-SWE-Bench fixes the prompt template, task set, container and evaluator, and varies only the harness through a shared adapter protocol [4]:

- The same backbone scores 19.1% with a minimal adapter and 73.4% with a full one.
- Across harnesses, Pass@1 shifts by up to 27.4 points under a fixed model.

The authors conclude that SWE-bench-style resolved rates conflate model, harness and task instances [4]. A paired study within a single harness varies only its configuration. Deterministic shortening of older tool results plus a rule-based stall detector raised complete solutions from 43 to 72 in a tight-context cohort, with model and tasks held constant [5]. A study of software-engineering agents reports two spreads on the SWE-bench Verified leaderboard: 19.4 points across harnesses under a fixed model, and 22.8 points across Claude models under a fixed harness. It also finds that the benefit of complex harnesses depends on task type and model strength [6]. The Holistic Agent Leaderboard similarly observes that scaffolds affect both accuracy and cost, yet cross-scaffold comparisons were rare in prior work [7].

These findings do not establish that harnesses dominate models in general. A position paper argues that, for long-horizon tasks across comparably capable frontier models, the harness is often the binding constraint on performance. On that basis it calls for harness disclosure and factorial evaluation [8]. By contrast, a credentialing study of eighteen agent configurations found support for model-quality differences, while harness-quality differences were inconclusive in its grid [9]. The evidence therefore supports a narrower claim: harness effects can be large, and their size depends on task, model and budget. For that reason they must be controlled and reported rather than assumed away.

The harness also matters beyond accuracy.

- **Security.** Indirect prompt injection exploits the fact that LLMs lack a formal way to separate instructions from data returned by tools [10]. This is a model-level weakness, but harness design decides how far it propagates. CaMeL shows that a system layer extracting control and data flow from the trusted query can secure an agent even when the underlying model remains susceptible [11].
- **Governance.** Harness mechanisms can create new failures. Context compaction has been shown to silently drop in-context governance constraints, raising violation rates from 0% to 30% across seven models [12].
- **Cost and latency.** Each context transformation can invalidate the KV cache and force re-prefill, causing latency spikes that a serving system must engineer around [13].

### The survey's lens: behaviour arises from model and harness together

We adopt the view that agent behaviour is a joint product of a model and its harness. The model contributes a stochastic policy. The harness constructs the context that policy sees, defines the actions it can take, and decides what happens to its outputs. This lens builds on several prior framings:

- CoALA's decomposition of language agents into memory, a structured action space and a decision-making loop [14].
- The profiling–memory–planning–action architecture of an earlier survey [15].
- A recent model–harness survey that defines an agent as a foundation model coupled with an execution harness and splits the harness into observation, context, control, action, state and verification/governance responsibilities [16].

Definitions of the harness itself vary in scope:

- OpenDev separates *scaffolding*, assembled before the first prompt, from the *harness*, the runtime layer for tool dispatch, context management and safety [17].
- HARBOR defines the harness as the structured execution environment governing tool access, artifact preservation, feedback and verification of progress [18].
- An enterprise case study frames it as a code-owned control layer that moves deterministic behaviour out of prompts and into manifests, schemas, contracts and validators [19].

We treat these as complementary emphases rather than competing definitions. Where the distinction matters, we note whether a mechanism acts before, during or after a model call.

### Scope and organisation

We focus on work in which the harness, rather than model training alone, is the object of design or measurement. Training methods enter only where they are coupled to harness mechanisms, for example reinforcement learning that integrates context compaction into rollouts [20]. The survey is organised around eight themes that together cover the harness stack:

1. **Agent loop architectures and conceptual frameworks.** ReAct-style loops, tree search over actions [21] and formal models of agents.
2. **Reflection, self-correction and verification.** This includes the unresolved debate over whether intrinsic self-correction helps without external feedback [22][23].
3. **Context and memory management.** From OS-style virtual context paging [24] to formal limits on compaction [25].
4. **Action and tool interfaces.** Code-as-action versus JSON calls [26] and protocol-mediated tool integration [27].
5. **Orchestration, multi-agent coordination and automated harness design.** Here reported multi-agent gains are contested once compute is matched [28], and harnesses can themselves be searched [29] or evolved at runtime [30].
6. **Execution platforms, sandboxes and serving infrastructure.** From open agent platforms [31] to production sandbox fleets for RL [32].
7. **Security, safety and governance.** Harness-level threats and defences.
8. **Evaluation methodology, harness effects and benchmark validity.** Cost-aware evaluation [33] and audits showing that leaked solutions and weak tests inflate SWE-bench results [34].

The eight themes are not disjoint. Compaction, for instance, is simultaneously a context mechanism, a serving cost and a safety surface. We cross-reference such cases rather than force them into a single category.

### Contributions

This survey makes four contributions.

1. **An organising lens.** It articulates and motivates the joint model–harness view, and positions it relative to existing agent surveys [15][35] and emerging harness-specific surveys [16][36].
2. **A comparative synthesis across the eight themes.** Within each theme, it contrasts design choices and their empirical support, rather than cataloguing systems.
3. **Cross-cutting interactions.** It highlights interactions that single-theme treatments miss. Examples are context compaction as a governance risk [12], defences that achieve near-zero attack success on static benchmarks but lose utility on dynamic-planning tasks [37], and memory injection as a hidden, depth-growing cost [38].
4. **Evaluation practice.** It consolidates methodological lessons, including controlling or disclosing the harness, reporting cost alongside accuracy, and auditing benchmark validity. It closes with open problems for treating the harness as a measurable, reproducible engineering artifact.

## 2. Background and Definitions

This section fixes the vocabulary used throughout the survey. It then traces how the notion of a *harness* emerged from early prompt-based agent loops. The definitions are organised around the survey's lens: control loops, conceptual architectures, context and memory, tool interfaces, orchestration, security, harness-aware evaluation, and automated harness design. Each term therefore anchors one or more later sections.

### From reasoning traces to the reason–act loop

The most direct ancestor of today's agent harnesses is ReAct. It prompts a frozen language model to interleave free-form reasoning traces with task actions whose results come back as environment observations [1][39].

ReAct's formal contribution is modest but consequential. The agent's policy conditions on a context of past observations and actions. Its action space is augmented from environment actions A to A ∪ L, where L is a space of language "thoughts". Thoughts do not affect the environment; they only update the context used for later reasoning or acting [1].

This framing explains why the loop, rather than the model alone, became the unit of design. The same frozen PaLM-540B behaves very differently depending on how its outputs are routed:

- **Reason-only** (chain-of-thought) prompting is ungrounded and prone to hallucination and error propagation. ReAct mitigates this by consulting a simple Wikipedia search/lookup API [1].
- **Act-only** prompting can fail to reason over long trajectories, for example by repeatedly issuing hallucinated actions in ALFWorld [1].
- **Interleaving the two** raised ALFWorld success from 45 to 71 and WebShop from 30.1 to 40 relative to act-only prompting [39].
- **Combining ReAct with CoT** gave the best HotpotQA and FEVER results among the prompting variants, though still far below supervised state of the art [39].

Two further features of the original work foreshadow later harness concerns:

- **Human intervention.** Editing a few reasoning traces let a human inspector rescue a failing trajectory, an early instance of human-in-the-loop control inside the loop [39].
- **Harness-generated training data.** ReAct trajectories from the large prompted model were used to fine-tune smaller models [39]. This anticipates the harness-in-the-loop learning discussed in the final category of our framework.

The loop's benefits are not domain-universal. Applying ReAct with tool calls to task-oriented dialogue on MultiWOZ, two related studies found a large gap in simulated success [40][41]:

- GPT-3.5 and GPT-4 agents reached 28.2 and 43.6 respectively.
- A handcrafted semantic-level dialogue manager reached 97.3.

The GPT-4 agent cost roughly 37 times more than GPT-3.5 for its improvement [40]. Human users nevertheless reported higher satisfaction with the ReAct systems [40][41]. We take this as an early signal that task success, cost and user experience can diverge depending on how the loop is instrumented and evaluated.

### Agents, architectures and the harness

We use **agent** to mean a system in which an LLM acts as the central controller, selecting actions in an environment over multiple steps. This follows the usage of surveys that contrast LLM agents with RL agents on the grounds of their natural-language interfaces and explainability [15].

Conceptual surveys decompose such agents into modules. One widely cited framework proposes profiling, memory, planning and action modules, with profiling shaping memory and planning, and all three shaping action [15]. The same survey separates two kinds of work:

- **Architecture design**, which it likens to choosing a network structure.
- **Capability acquisition**, which it likens to learning parameters and which may or may not involve fine-tuning [15].

This distinction is useful here. Harness engineering is largely the architecture-design half, carried out around a model whose weights are often fixed. A later systematic review similarly places ReAct, Reflexion and Toolformer in a single-agent category defined by decision loops over planning, memory and tool use [35]. It also notes that such systems often struggle when context tracking, external memory and adaptive tool use must be combined in dynamic environments [35]. That weakness motivates the context-management and orchestration mechanisms surveyed later.

The **harness** is the part these module taxonomies leave implicit. We adopt HARBOR's definition: the structured execution environment around an LLM agent that defines how it accesses tools, preserves artifacts, observes feedback and verifies progress [18]. HARBOR makes this concrete as a tuple of agents, commands, mutable artifacts, verifiable gates and reusable knowledge [18]. It also argues two points:

- Many long-horizon failures stem from *underspecified executions*, in which agents lack the tools, abstractions and feedback needed to pursue high-level goals [18].
- Externalising workflow state into persistent artifacts reduces reliance on transient context [18].

We use **scaffold** for the model-facing portion of the harness: prompts, thought formats, prescribed reasoning procedures and few-shot trajectories. The dialogue studies above are a clear example. Their prompts prescribed an explicit step sequence and included example conversations layered on the ReAct format [40][41].

The harness is the broader runtime. Besides the scaffold, it includes tool routing, state persistence, observability, verification and sandboxing. The same dialogue systems, for instance, used Langfuse to trace reasoning and track API cost [41].

### Tools, environments and interfaces

A **tool** is an action whose execution is mediated by the harness and whose result is returned as an observation. **Tool interfaces** are the design choices about which actions to expose and at what granularity. Examples range from ReAct's two-verb Wikipedia API [1] to the domain-specific dialogue toolset of list_domains, list_slots, db_query and a booking-reference generator [41]. The latter constrained the model to database contents without delexicalised templates [40].

The **environment** is whatever the tools act upon: a knowledge source, a simulated household or shop, a user, or a containerised code repository. Environment design and harness design blur in practice. USEbench, for example, wraps heterogeneous software-engineering benchmarks behind a unified Docker-based interface for reading files and executing commands. This reduces per-benchmark adaptation [42] and shows that the evaluation harness is itself an engineered artifact.

### Control loops beyond a single agent

We reserve **control loop** for the policy that decides, at each step, what to feed the model and what to do with its output. In ReAct, this loop is a single alternation of thought, action and observation [1].

Later systems nest or compose loops:

- **Multi-agent role assignment.** Systems such as MetaGPT and CAMEL use role assignment and structured communication among agents [35].
- **On-the-fly workflows.** Software-engineering agents have traditionally used fixed pipelines, such as AutoCodeRover's fault localisation followed by patch generation. USEagent instead places a Meta-Agent above sub-agents that builds workflows on the fly, backed by a structured consensus memory of project state [42]. It reports 33.3% on USEbench versus 26.8% for an unmodified OpenHands CodeActAgent baseline, while remaining close to the specialised AutoCodeRover on SWE-bench-verified [42].
- **Gated staged pipelines.** HARBOR dispatches context-isolated subagents through bounded stages. It advances only when executable gates, such as import checks and rollouts, pass [18]. The authors caution that such gates turn many failures into observable ones without guaranteeing semantic correctness [18].

### The harness as an object of search

Once agents are written as code, the harness itself becomes a search space. Automated Design of Agentic Systems (ADAS) frames this as a research area. Its Meta Agent Search method has a meta agent iteratively program new agents, conditioned on a growing archive of prior designs [43][44]. Because code is Turing-complete, this space can in principle express any combination of prompts, tool use and workflows [43]. The authors conjecture that hand-designed agentic systems may eventually give way to automatically designed ones [44].

Seen against ReAct, the lineage is clear. What began as a single hand-written prompt format that reroutes model outputs has become a layered runtime of scaffolds, tools, memory, gates and orchestrators, and that runtime is increasingly engineered, evaluated and optimised in its own right.

## 3. A Framework for Harness Components

Existing conceptual framings of language agents already decompose them into parts. CoALA organises agents by modular working and long-term memory, an internal/external action space, and a decision loop of planning and execution [14]. A widely used survey instead proposes profiling, memory, planning and action modules [15]. Aviary formalises agent tasks as language-grounded POMDPs and represents agents as stochastic computation graphs whose prompts, memories and weights can be optimised [45]. These framings describe the *agent*. Harness engineering needs a view that also separates out the *runtime around the model*. Two recent formulations point that way. One treats the harness as a closed-loop controller acting on harness-constructed context, with the LLM as a stochastic open-loop policy [8]. HARBOR defines a harness as the structured execution environment that governs tool access, artifact preservation, feedback observation and progress verification [18].

We synthesise these into six layers, ordered from innermost to outermost: control loop, action interface, context, memory, execution environment and orchestration. Three concerns cut across all layers: security, evaluation and automated design.

### Layer 1: The control loop

The innermost layer decides how reasoning, actions and observations are interleaved. ReAct formalises this layer by augmenting the action space with language "thoughts" that update context without touching the environment [1]. Later work keeps the model frozen but changes the loop around it:

- **Reflexion** adds an evaluator and a self-reflection model whose verbal feedback conditions later trials [2].
- **LATS** replaces the single trajectory with Monte Carlo Tree Search, using LM value functions [21].

The three approaches differ in where they spend extra inference: across trials (Reflexion) or across branches within a trial (LATS). Transplanting the loop to new domains is not automatic. ReAct agents underperform classical dialogue managers on simulated MultiWOZ success, yet users rate them as more satisfying [41].

### Layer 2: The action interface

This layer determines what the model can do. SWE-agent argues that LM agents are a new class of end user and shows that purpose-built agent-computer interface commands substantially change coding performance [46].

Two lines of work make the interface dynamic rather than fixed:

- **ScaleMCP** retrieves MCP tools into context during multi-turn interaction, motivated by provider limits on how many tools can be equipped at once [27].
- **Live-SWE-agent** starts from a bash-only scaffold and lets the agent synthesise its own tools at runtime [30].

### Layer 3: Context

Context management governs what occupies the finite window at each step. The approaches differ mainly in how lossy and how model-dependent they are:

- **Pruning to recent tool pairs.** Keeping only the most recent tool call/response pairs, plus summaries of evicted pairs, raised task completion over full history while using far fewer tokens [47].
- **Deterministic eviction.** CWL evicts over an agent-annotated episode dependency graph, which avoids compression-induced hallucination [48].
- **Parallel summarisation.** Summarising blocks in parallel targets the blocking cost and unpredictability of sequential summarisation [49].
- **Deterministic shortening.** Shortening older tool results, combined with stall detection, changes outcomes for unchanged model weights [5].

Context handling also reaches down into serving. SmoothAgent shows that each context transformation invalidates the KV cache, and precomputes transformed caches to cut time-to-first-token spikes [13].

### Layer 4: Memory

Memory holds state that persists beyond the window. The boundary with context is porous. MemGPT pages information between the window and recall/archival stores, and the model directs this paging through function calls [24].

Other work varies what is stored and how it is retrieved:

- Reflexion's episodic reflections are later moved into FAISS-backed stores with quality filtering [50].
- PsychoAgent separates factual and affective streams and re-ranks affective memories by salience [51].

Memory also has a measurable cost. Injected memory tokens grow with workflow depth, reaching 27.6% of cost at depth six in one enterprise benchmark [38].

### Layer 5: Execution environment

This layer covers where actions run and who is trusted:

- **Sandboxed platforms.** OpenHands provides sandboxed code execution and integrated benchmarks [52].
- **Environment management.** USEAgentPlus identifies environment management itself as a key barrier and adds dedicated tooling for it [53].

This layer is also where trust boundaries sit. MCP's self-asserted capabilities and provenance-free context amplify attacks [54]. AgentDojo evaluates injection through tool outputs using state-based checks [10].

### Layer 6: Orchestration

The outermost layer composes multiple loops. The main designs are:

- **Conversation programming.** AutoGen programs control flow as conversations among conversable agents [55].
- **Meta-agent orchestration.** USEagent's meta-agent builds workflows on the fly over a shared consensus memory [42].
- **Staged pipelines.** HARBOR advances stages only through executable gates, using persistent artifacts as the communication substrate [18].

MAST suggests that this layer is where many failures originate. It attributes 44.2% of multi-agent failures to system design [56].

### Cross-cutting concerns

Three concerns span every layer rather than belonging to one.

**Security.** Guardrails intervene at different layers:

- PromptArmor sanitises inputs before they reach the agent [57].
- MELON re-executes the trajectory with a masked prompt and compares tool calls [58].
- AgentDyn shows that defenses tuned on static tasks become insecure or over-defensive when tasks require dynamic planning [37].

**Evaluation.** Harness effects can be large relative to model effects. Under a fixed model, the best and worst harnesses differ by 19.4 pp, close to the 22.8 pp spread across models [6]. Separately, simple baselines can match complex agent architectures at much lower cost [33].

**Automated design.** This concern turns the harness itself into the object of optimisation:

- ADAS searches over agent code using a growing archive of discovered designs [29].
- CompactionRL trains summarisation inside RL rollouts [20].
- Re-ReST self-trains on trajectories repaired using environment feedback [59].

### Comparison of representative works

| Work | Primary harness layer | Adaptation mechanism | Context/memory strategy | Evaluation setting | Headline evidence (as reported) |
|---|---|---|---|---|---|
| ReAct [1] | Control loop | Few-shot prompting of frozen model | Full trajectory in context | HotpotQA, FEVER, ALFWorld, WebShop | +34/+10 abs. success on ALFWorld/WebShop |
| Reflexion [2] | Loop + evaluator + reflection | Verbal feedback across trials | Trajectory + episodic reflections | HumanEval, AlfWorld, HotpotQA | 91% pass@1 HumanEval |
| LATS [21] | Search over loop | MCTS with LM value function | Tree of trajectories | Programming, QA, web, math | 92.7% HumanEval; 75.9 WebShop |
| MemGPT [24] | Memory tiers | Self-managed via function calls | Paging, recursive summary | Documents, multi-session chat | No numbers in excerpt |
| SWE-agent [46] | Action interface | Hand-designed ACI | Interface-shaped observations | SWE-bench, HumanEvalFix | 12.5% / 87.7% pass@1 |
| Live-SWE-agent [30] | Self-evolving tools | Runtime tool synthesis | Minimal bash scaffold | SWE-bench Verified, Pro | 77.4% / 45.8% |
| OpenHands [52] | Platform/sandbox | Pluggable agents, multi-LLM | Platform-dependent | 13–15 tasks incl. SWE-bench, WebArena | No scores; 1,096 citations [60] |
| AutoGen [55] | Multi-agent orchestration | Conversation programming | Per-agent message context | Math, coding, QA, OR | No numbers in excerpt |
| USEagent [42] | Meta-agent orchestration | On-the-fly workflows | Consensus project-state memory | USEbench (1,271 tasks) | 33.3% vs 26.8% CodeActAgent |
| HARBOR [18] | Gated staged pipeline | Isolated subagents | Persistent artifacts | 6 robot RL benchmarks | No numbers in excerpt |
| Less Context [47] | Context policy | Pruning + summarization | Last N tool pairs | Live ERP via MCP | 91.6% vs 71.0%, ~63% fewer tokens |
| CWL [48] | Context eviction | LLM-free eviction | Episode DAG | 89 tasks, 80M tokens | No measurable degradation (initial) |
| CompactionRL [20] | Compaction in training | PPO on task + summary | Structured summary + recent steps | SWE-bench Verified, TB2 | 66.8% (+7.0) Verified |
| SmoothAgent [13] | Serving layer | Lookahead KV precompute | Non-blocking transformations | Multiple frameworks | Up to 11.9x TTFT cut |
| ADAS [29] | Whole design | Meta agent writes code | Per discovered agent | DROP, MGSM, transfer | +13.6 F1, +14.4% MGSM |
| AgentDojo [10] | Security benchmark | N/A | Stateful injection placeholders | 97 tasks, 629 cases | <66% benign; detector 8% ASR |
| PromptArmor [57] | Input guardrail | Detect and strip injections | Sanitised tool data | AgentDojo | <1% ASR vs 55% undefended |
| MELON [58] | Execution-level defense | Masked re-execution | Tool call cache | AgentDojo, 3 models | Lowest ASR; figures missing |
| AttestMCP [54] | Protocol trust boundary | Attestation + authentication | N/A | 847 scenarios | 52.8%→12.4% ASR |
| Yuj [5] | Closed-loop controls | Shortening + stall detection | Age-tiered shortening | SWE-bench Verified/Pro, FeatureBench | F2PF 28%→49% |
| NanoHarness [6] | Component ablation | Add components singly | Compression as component | 60 configurations | 19.4 vs 22.8 pp gaps |
| MAST [56] | Multi-agent failure analysis | Taxonomy + LLM judge | N/A | 1,642 traces | 41–86.7% failure rates |

The thematic sections that follow take these layers roughly from the inside out, then return to the cross-cutting concerns of security, evaluation and automated design.

## 4. Control Loops and Planning Scaffolds

The control loop is the harness's central decision about how often the model reasons, when it acts, what it observes, and when it stops. The designs below differ along three axes. The first is how much deliberation happens before each action. The second is whether failed attempts feed back into later attempts. The third is who decides that the loop is finished. We treat single-step reasoning–acting loops, explicit planning scaffolds, reflection loops, and tree search as points along these axes. Their termination and retry policies are often left implicit, but they are part of the design.

### The single-step reasoning–acting loop

The baseline design interleaves one thought, one action and one observation per step. Much later machinery is built on top of it. Reflexion's Actor is instantiated as either chain-of-thought or ReAct [2]. Re-ReST generates ReAct-style thought–action trajectories as its raw material [59].

The loop's simplicity is also its limitation. The LATS authors argue that reliance on simple acting processes limits LMs' deployment as autonomous agents [21].

A study of ReAct prompting for task-oriented dialogue on MultiWOZ shows how the loop behaves outside the benchmarks where it was developed:

- **Simulated users.** Over 1,000 simulated dialogues, ReAct agents reached success rates of 28.2 with GPT-3.5 and 43.6 with GPT-4. Two classical baselines did much better: 83.8 for a BERT NLU + handcrafted policy + template pipeline, and 97.3 for a semantic-level handcrafted policy [40].
- **Cost.** The GPT-4 improvement came at roughly 37 times the cost ($2,258.81 versus $61.71). The authors judged this not justified [40].
- **Human users.** With human evaluation, the gap narrowed. Users rated the ReAct agent higher on satisfaction despite its lower success rate [40].

This evidence says that a bare reasoning–acting loop over tools is a weak controller for structured, multi-turn tasks. It does not say whether the fault lies in the loop, the model, or the tool design. Notably, the same system already layers a prescribed five-step reasoning procedure and few-shot trajectories on top of ReAct [40]. That is a light form of fixed planning scaffold inside the single-step loop.

### Planning scaffolds and searched loop designs

Plan-and-execute designs move deliberation ahead of action. A planner commits to a decomposition, and an executor carries it out step by step. The sources gathered for this section do not include direct evaluations of dedicated planner architectures. We therefore do not make comparative claims about them here.

What the evidence does show is that the space of loop structures is large enough to search automatically. Automated Design of Agentic Systems (ADAS) represents an entire agentic system in code. A meta agent then iteratively proposes, evaluates and archives new designs [29]. The discovered agents beat hand-designed baselines by 13.6 F1 on DROP and 14.4% on MGSM. They also kept their advantage when transferred across domains and models [29].

The authors argue that searching in code space, rather than over prompts alone, exposes design patterns that prompt-only search cannot reach [29]. For loop design, the implication is that the choice among ReAct, planning and reflection structures need not be made by hand. It can itself be optimized against an evaluation function. That function may target cost, latency or safety as well as accuracy [29].

### Reflection as an outer loop

Reflection adds a second, slower loop around the acting loop. Reflexion splits the harness into three components:

- an Actor, which generates text and actions;
- an Evaluator, which scores trajectories by exact match, heuristics, LLM judgment or self-written unit tests;
- a Self-Reflection model, which turns sparse rewards into verbal feedback stored in episodic memory for later trials [2].

The outer loop yields absolute gains of 22% on AlfWorld over 12 iterative steps and 20% on HotPotQA. It also reaches 91% pass@1 on HumanEval [2]. The authors acknowledge that the approach depends on the model's self-evaluation ability and offers no formal guarantee of success [2].

Follow-up work treats the reflection memory as infrastructure. One extension replaces text storage with a FAISS-backed vector store. It also filters reflections through semantic screening and LLM validation before they are written to memory [50]. That extension reports no quantitative results in the available text.

Whether the Evaluator can be the model itself is the crux of the design. Huang et al. find that LLMs struggle to self-correct reasoning without external feedback, and that performance can degrade after intrinsic self-correction [22]. Two lines of work respond to this finding:

- **Better verification prompts.** ProCo masks a key condition in the question and asks the model to recover it as a verification step. With GPT-3.5-Turbo-1106, it gains 6.8 exact match on open-domain QA, 14.1 accuracy on arithmetic and 9.6 on commonsense reasoning over a Self-Correct baseline [23]. This suggests the verification prompt, not only the feedback source, determines whether intrinsic correction helps.
- **Prompt sensitivity.** Work on vision-language models similarly finds inference-time self-correction highly sensitive to prompt formulation. Without fine-tuning or external feedback it is largely ineffective [61].

CorrectBench offers a broader picture across 11 correction methods, including Reflexion:

- correction helps most on complex reasoning;
- chaining methods adds accuracy at an efficiency cost;
- a plain chain-of-thought baseline remains competitive;
- reasoning models such as DeepSeek-R1 gain little and incur high time costs [62].

A different placement moves the reflector out of the inference loop altogether. Re-ReST uses a reflector with environment feedback, such as unit-test results, to repair failed trajectories. The repaired trajectories become self-training data. Environment feedback is needed only during training, not at inference [59]. This adds 2.0% on HotpotQA and 14.1% on AlfWorld beyond plain self-training [59]. The paper does not measure inference-time cost against Reflexion-style loops, so the trade-off is shown for where feedback is required, not for compute.

### Tree search over actions

Tree search replaces a single committed trajectory with exploration over alternatives. LATS runs Monte Carlo Tree Search over LM-generated actions. It uses three signals:

- LM-powered value functions to score nodes;
- self-reflections to guide exploration;
- environment feedback as an external signal [21].

The authors present it as the first general framework combining reasoning, acting and planning [21]. They report 92.7% pass@1 on HumanEval with GPT-4. They also report an average score of 75.9 on WebShop with GPT-3.5, which they describe as comparable to gradient-based fine-tuning [21].

The HumanEval figure sits close to Reflexion's 91% [2]. The two results were not obtained under matched model versions or compute budgets, so the small gap should not be read as the marginal value of search. The clearer contrast is structural. Reflexion retries whole episodes sequentially and carries lessons forward in memory. LATS branches within an episode and backs up value estimates. This requires the environment to permit revisiting states, and it multiplies model calls per decision.

### Termination, retry and budget policies

Every loop above needs a stopping rule, and several of the reported gains are functions of that rule:

- Reflexion's AlfWorld result is stated over a fixed horizon of 12 iterative trials [2].
- Re-ReST samples k=3 outputs per instance and permits a single reflection iteration [59].
- CorrectBench's finding that stacked correction reduces efficiency, and yields little for reasoning models, makes retry depth a cost decision rather than a free improvement [62].

Termination can also fail at the level of the interaction partner. In the MultiWOZ study, an LLM-based user simulator failed to end conversations correctly and sometimes switched roles, so the authors abandoned it for an agenda-based simulator [40].

Evaluation infrastructure increasingly fixes such limits outside the harness under test. Claw-SWE-Bench, for example, holds the per-instance timeout constant while swapping harnesses. Under that protocol, harness choice alone shifted Pass@1 by up to 27.4 points for a fixed model [4].

### Trade-offs

Taken together, the evidence suggests the following trade-offs:

- **Single-step loops** are cheap and general, but weak on structured tasks without added scaffolding [40].
- **Reflection** buys cross-trial improvement, but its reliability tracks the quality of the evaluator signal. External or carefully constructed verification helps, while naive intrinsic critique can hurt [22][23].
- **Tree search** reaches strong scores [21] at a cost in calls and environment assumptions that current reports do not normalize.

Because harness differences can rival model differences [4], comparisons among loop designs are only meaningful when budgets, stopping rules and feedback sources are reported alongside accuracy.

## 5. Tool and Action Interfaces

If the loop architecture decides *when* an agent acts, the action interface decides *what* it can do and how cleanly the effects of an action come back to it. The works reviewed here treat the interface as its own design variable: the command vocabulary, the format of calls, how tools are found and supplied, and how call correctness is checked. Taken together, they show that interface choices change both capability and reliability, even when the model and the tool set stay fixed.

### Agent-computer interfaces as purpose-built affordances

SWE-agent gives this view its clearest statement. It argues that LM agents are a new category of end user that benefits from interfaces built for them, much as human programmers benefit from IDEs [46]. Its agent-computer interface (ACI) sits between the model and the operating system. It offers commands for creating and editing files, navigating repositories and running tests. The authors report that ACI design significantly affects the agent's ability to carry out these operations [3]. The interactive agent reached 12.5% pass@1 on SWE-bench and 87.7% on HumanEvalFix, well above earlier non-interactive LM results [46].

That comparison sets an interactive, interface-equipped agent against non-interactive baselines. It therefore mixes the benefit of interaction with the benefit of a particular command design. Later harness-controlled evaluations isolate the interface more directly. In Claw-SWE-Bench, the same GLM 5.1 backbone scores 19.1% Pass@1 with a minimal direct-diff adapter and 73.4% with the full adapter [4]. That gap comes purely from the interface layer.

Unified interfaces also matter on the evaluation side. USEbench wraps 1,271 repository-level tasks behind a common docker-based API for reading files and executing commands, which reduces per-benchmark adaptation work [42].

### Code as action versus structured tool calls

The most sustained comparison in this literature is between executable code and JSON or text tool calls.

**CodeAct.** CodeAct replaces JSON and text actions with Python executed by an interpreter [26]. The authors argue that JSON and text formats constrain the action space and cannot compose several tools in one action. Code, by contrast, supports control and data flow natively: intermediate results are stored as variables, and tools are chained through loops and conditionals [26].

Across 17 LLMs, CodeAct reached up to 20% absolute higher success on M3ToolEval, an 82-task multi-tool benchmark, while using up to 30% fewer actions [63]. It was comparable or better on API-Bank's atomic tool calls for most models [63]. The gains widened as model capability increased [26]. Interpreter tracebacks also double as automatic feedback, which let agents self-debug without human-curated feedback [26]. This links the interface directly to the verification mechanisms discussed elsewhere in the survey.

**Programmatic tool calling on BFCL.** A later study reaches a similar conclusion under tighter controls. It compares tools exposed as typed Python stubs against native JSON calling across 14 LLMs on a 309-entry subset of BFCL v4. A stop middleware equalizes the number of LLM calls between conditions [64].

- Programmatic calling matched or exceeded JSON in 11 of 14 models.
- Its advantage on sequential tasks grew with chain length, reaching an 18.8% absolute gap. The authors attribute this to the extra inference turn that JSON calling needs for each link.
- JSON calling dropped calls entirely above a model-specific fan-out threshold, while programmatic calling kept enumeration accuracy.
- Under context flooding, JSON degraded by 2.3% on average and a filesystem-discovery condition by 32%, while programmatic calling stayed stable [64].

The study also qualifies CodeAct's framing. Whether programmatic calling works well split along model-generation lines rather than model family [64]. The code-action advantage is therefore conditional on the model, not universal.

**Beyond software engineering.** SpatialClaw extends the comparison to vision-language agents. It contrasts single-pass code, structured tool calls and an iterative, persistent Python kernel [65]. The authors identify a distinct weakness in each alternative:

- Single-pass code forces the agent to commit to a complete strategy before it sees intermediate results.
- Structured tool calls limit free composition of tool outputs with libraries such as numpy and scipy.

The persistent-kernel design averaged 59.9% across 20 spatial benchmarks, 11.2 points above a recent spatial agent. The gains held across six backbones and persisted when predefined utility wrappers were removed. The authors read this as evidence that the interface, rather than model-specific tuning, drives the improvement [65].

Taken together, these three studies suggest that two properties explain the code-versus-JSON gap better than syntax does:

- **Statefulness:** variables persist across steps.
- **Composition within a turn:** several tools can be chained without extra model calls.

### Supplying tools at scale: retrieval and MCP

As tool catalogs grow, the harness must decide which tools enter the context at all. ScaleMCP is motivated by the limit providers place on how many tools can be equipped at once, which it cites as 128 [27]. It gives the agent an MCP retrieval tool. The agent can re-query this tool during multi-turn interaction, rather than having tools selected once before invocation, a practice the authors argue limits autonomy [27].

The tool index treats MCP servers as the single source of truth. It stays synchronized by hashing each tool's name, description and parameters and applying CRUD updates [27]. A weighted embedding scheme emphasizes chosen parts of the tool document, such as the name or synthetic questions [27]. The evaluation covers 5,000 financial-metric MCP servers, 10 LLMs and several retrievers. The paper reports improvements in retrieval and invocation, but the available excerpt gives no figures, so the size of the benefit cannot be judged from it [27].

Standardizing tool supply through a protocol also changes the attack surface. A formal analysis of the MCP specification identifies three protocol-level weaknesses [54]:

- capability declarations are self-asserted and unverified;
- servers can use sampling to inject prompts in the user role;
- outputs from multiple servers are merged in the context without provenance.

Across 847 attack scenarios, MCP amplified attack success by 23–41% relative to equivalent non-MCP integrations. A proposed attestation extension cut success from 52.8% to 12.4%, at a median overhead of 8.3ms per message [54]. The interface that makes tools easy to plug in thus also makes provenance harder to establish. The security section of this survey takes this tension up in more detail.

### Runtime tool synthesis

The works above treat the tool set as given. Live-SWE-agent instead lets the agent write its own tools during a run. It starts from a bash-only scaffold and adds tool-creation instructions and examples to the initial prompt. After each environment feedback, a reflection message asks whether creating or revising a tool would help [30].

The system reports 77.4% on SWE-bench Verified and 45.8% on SWE-Bench Pro without test-time scaling [30]. On a 60-task subset it reports 65.0% versus 53.3% for DGM, an offline self-improving system cited as costing about $22,000 per run [30]. According to its ablations, tool creation raised solve rates, and the reflection prompt was necessary for useful tools to appear. The overhead is described only as minimal, without quantification here [30].

This places interface design on a continuum with automated harness design. ADAS likewise relies on code as a representation expressive enough to cover prompts, tool use and workflows [43].

### Measuring and rewarding correct calls

Reliability claims depend on how call correctness is judged. BFCL uses Abstract Syntax Tree (AST) evaluation, which scales to thousands of functions. It covers serial and parallel calls across programming languages, plus stateful multi-step settings that include abstention [66]. Its headline finding is that state-of-the-art models do well on single-turn calls but struggle with memory, dynamic decision-making and long-horizon reasoning [66].

FC-RewardBench, built from BFCL-v3, locates where errors concentrate. Wrong parameter values (650 cases) outnumber wrong function names (403) and wrong numbers of functions (245) [67]. Most failures are therefore subtle argument errors rather than choosing the wrong tool. General-purpose reward models miss these signals. Dedicated outcome reward models yielded up to 25% average improvement across seven out-of-domain benchmarks under Best-of-n selection [67].

### Open gaps in this section's coverage

The evidence reviewed here has limits. It does not directly measure how sensitive agents are to the wording of tool descriptions or to prompt formatting. It also does not cover the earlier lineage of self-taught and retrieval-augmented API-calling models, beyond their use as benchmarks such as API-Bank. Both gaps matter for any claim about how robust an interface is.

## 6. Context Engineering and Memory

Every long-horizon agent must decide what occupies its finite context window at each step and what is moved outside it. Within the organising lens of this survey, context and memory management sits between the control loop and the action interface. CoALA already treats memory, split into working and long-term stores, as one of the three axes along which language agents are described, alongside the action space and the decision loop [14]. It also frames memory reads and writes as internal actions [68]. Practitioner reports make the same point from the engineering side. OpenDev defines the harness as the runtime layer responsible for tool dispatch, context management and safety. It lists finite context windows among the core problems a terminal coding agent must solve, and it answers with adaptive compaction of older observations, event-driven reminders against instruction fade-out, and cross-session memory [17]. SmoothAgent likewise describes reduction, offloading and isolation strategies as a fundamental component of harness development [13].

The motivation is not only the hard token limit. Several works invoke "context rot", the observation that reliability degrades as context grows even inside the supported window [13]. One formal treatment argues that this defines an *effective* context window below the nominal one, which pushes agents to compact early [25]. CompactionRL similarly reports that scaling context length alone is costly and does not fully fix degraded utilisation over long sequences [20].

### Compaction by summarisation and its limits

The canonical design is threshold-triggered LLM summarisation. MemGPT set out an operating-system analogy. Its main context holds system instructions, an editable working context and a FIFO message queue. A queue manager issues a memory-pressure warning at about 70% of the window, so the model can save important facts. On overflow it evicts messages, replaces them with a recursive summary, and keeps the originals retrievable from recall storage through function calls [24]. Later production agents follow a similar trigger-and-summarise pattern. One analysis reports that Claude Code, Cursor and Codex compact when usage passes a threshold such as 95% [25]. The authors of CWL characterise 70–90% triggers as the dominant approach, though this is their own assessment rather than a measured survey [48].

Summarisation is lossy, and three lines of work quantify this in different ways.

- **Theory.** Context Compaction Theory models a single compaction call as a game. It proves that the minimum budget for generation-based compaction equals one-way randomised communication complexity. It also shows that selection-based compaction can need Θ(log n) more budget for some query families [25]. In the same paper's case study, Anthropic's compaction endpoint answered membership queries over 15,000 items with error near random guessing, far worse than a Bloom filter of the same size [25].
- **Operational reliability.** The parallel-compaction study reports three problems with summarisation. Models largely ignore length instructions. Summary length and retained content fluctuate across runs. The blocking call can stall inference for tens of seconds [49]. Its remedy is to summarise blocks in parallel. The authors report lower wall time and higher throughput at matched decode volume on HotpotQA and LoCoMo, though the abstract gives no figures [49].
- **Training.** CompactionRL starts from a different observation. During RL rollouts, the summary determines everything the later policy can see, so summarisation should be learned rather than bolted on at inference time. The method jointly trains execution and structured summaries under a shared reward, using PPO with cross-trajectory GAE to carry credit across compaction boundaries. It reports gains over inference-time compaction baselines: +7.0 points on SWE-bench Verified for GLM-4.5-Air and +6.8 on Terminal-Bench 2.0 for GLM-4.7-Flash [20].

### Pruning and structured eviction

A contrasting family avoids model-generated summaries altogether. On a live ERP expense-itemisation benchmark, keeping only the last five tool call/response pairs raised complete itemisation from 71.0% with full history to 79.0%, while using 535,274 rather than 1,480,996 tokens. Adding summarisation of evicted pairs reached 91.6% with 553,374 tokens [47]. The authors argue that evicting whole tool pairs preserves structured form state, which token-level prompt compression can corrupt. They explicitly limit their conclusion to this class of enterprise workflow rather than claiming that less context is universally better [47].

CWL goes further toward determinism. The agent annotates its trajectory as a typed, dependency-linked episode graph. An LLM-free policy then evicts the most recoverable content first, for example actions whose effects already persist in the environment. User turns are never evicted, and causal dependencies take precedence over recency [48]. CWL rules out compression-induced hallucination by construction. It reports one session of 89 tasks over 80 million tokens without measurable accuracy loss, which the authors themselves call preliminary [48]. They contrast it with Context-Folding, which learns branch-and-return folding through FoldGRPO but requires model-specific fine-tuning and still retains model-written summaries [48].

These designs trade off along a common axis. At one end, learned summaries [20] promise adaptivity. At the other, deterministic eviction [48] and pair-level pruning [47] offer predictability and verbatim fidelity.

### Long-term memory stores

Outside the window, memory becomes a retrieval and consistency problem. MemGPT's recall and archival tiers are self-managed by the model through function calls [24].

MOSAIC criticises MemGPT, Mem0, A-Mem and MemOS as append-only stores that silently accumulate contradictions [69]. Its alternative has three parts:

- a typed entity graph;
- locality-sensitive-hashing retrieval in place of LLM classification;
- conflict detection at ingestion.

It reports 89.35% on LoCoMo, 27.21 points above Mem0. It also detected 66% of injected clinical-guideline conflicts versus 14% for the best baseline [69].

PsychoAgent attacks a different weakness of similarity-based retrieval. It re-ranks affective memories by salience after semantic preselection, and in three controlled scenarios this retrieved more conflict-critical memories. Its human ratings, however, showed no significant differences after correction [51].

A more harness-centric answer comes from LongMemEval-V2. There, storing trajectories as files and letting a coding-agent harness gather evidence (AgentRunbook-C) reached 72.5% accuracy. This compares with 48.5% for the strongest RAG baseline and 69.3% for plain Codex, which was also much slower [70]. The result suggests that memory management can itself be recast as tool-mediated file management.

### Evaluating memory

Benchmarks have shifted from chat recall toward agent experience.

- **LongMemEval** tests extraction, multi-session and temporal reasoning, knowledge updates and abstention. It finds 30–60% drops for long-context LLMs. It also shows that fact-augmented keys, time-aware query expansion and structured reading each help, and that reading is hard even with perfect recall [71].
- **Memora** argues that such benchmarks are shallow. By its count, 94% of LoCoMo and 85% of LongMemEval questions need evidence from at most two sessions [72]. It introduces a forgetting-aware metric that penalises reliance on invalidated memories, and reports only marginal gains from memory agents under heavy mutation [72].
- **LongMemEval-V2** targets environment-specific workflows and "gotchas" drawn from web-agent trajectories of up to 115M tokens [70].

### Side effects: latency and safety

Context transformation also has costs beyond lost information. Each rewrite of the context invalidates the KV cache and forces re-prefill, which produces spikes in time to first token (TTFT). SmoothAgent notes that most transformations are segment-decomposable and precomputes them asynchronously, cutting TTFT at transformation points by up to 11.9x [13].

More seriously for governance, compaction can erase constraints. On ConstraintRot, compaction raised violation rates from 0% to 30% across seven models. Constraints placed in the preserved system message showed no decay. An attacker controlling only ingested data can bias the summariser into deleting a policy, an attack the paper calls Compaction-Eviction [12]. Pinning 47 tokens of constraints restored 0% violation in the reported setting, although naive pinning still failed in some cases [12]. Context management is therefore also a security surface, which links this category directly to the harness-level safety concerns discussed later in the survey.

## 7. Execution Environments and Sandboxing

Every action an agent takes, whether a shell command, a file edit, a browser click or an MCP tool call, runs in some runtime substrate. That substrate sets what the agent can reach, what persists between steps, and how much damage a mistaken or adversarial action can do. This section relates execution environments to the other layers of the harness. Sandboxes shape the action interface. They also produce the signals that verification and RL rely on, and they form the last line of defense when security controls higher in the stack fail.

### Sandboxed platforms as the harness substrate

Open agent platforms treat the sandbox as a first-class component rather than an afterthought.

- **OpenHands** gives agents a platform where they act like developers by writing code, using a command line and browsing the web. It pairs sandboxed environments for safe code execution with interfaces for implementing new agents, plugging in different LLMs and coordinating multiple agents [52][31]. The sandbox is packaged with a benchmark integration layer covering SWE-Bench and WebArena, so the same execution substrate serves both development and evaluation. The two versions of the paper report 13 and 15 evaluation tasks respectively [52][31]. Later benchmarks, including TheAgentCompany, RExBench and FreshBrew, cite the platform [60].
- **SWE-agent** approaches the same substrate from the interface side. It argues that the agent-computer interface layered between the model and the computer significantly affects how well agents edit code, navigate repositories and run tests. It reports 12.5% pass@1 on SWE-bench with a custom interface [3].

The contrast is instructive. OpenHands emphasizes a general, safe execution host. SWE-agent shows that the commands exposed inside that host are themselves a performance lever. The sandbox and the action interface are therefore coupled design decisions.

The environment is not always a passive container that the agent merely inhabits. Work on moving coding agents from patching to systems integration identifies environment management as the key technical barrier [53]. Agents struggle to install dependencies, run commands in the wrong order or location, and fail to recognize environment-changing commands.

USEAgentPlus responds by adding three things [53]:

- an environment-probing stage that writes build/test commands and package information into shared memory;
- tools for version control and dependency management;
- a recommendation that agents run CI-like checks before submitting.

It reports executing 60% of 50 open-source projects by composing Bash scripts for a fresh environment [53]. Here the sandbox's mutable state becomes something the agent must model explicitly, linking execution infrastructure to context and memory management.

### Isolation boundaries and how they fail

The isolation technology behind these platforms varies widely. According to the SandboxEscapeBench authors, much of the open-source agent ecosystem and local developer tooling relies on standard Docker isolation, while hyperscale providers use microVMs or gVisor [73]. DSec, DeepSeek's production sandbox platform, makes this heterogeneity explicit. It exposes function-call, container, microVM and full-VM backends through one SDK, on the premise that agentic workloads have heterogeneous isolation needs [32].

Whether containers are an adequate boundary is now an empirical question. SandboxEscapeBench runs models with shell access inside a container nested within a VM whose outer layer has no known vulnerabilities. This lets escape attempts be measured without endangering evaluation infrastructure. The benchmark spans 18 scenarios across orchestration, runtime and kernel layers [73].

Its findings:

- Frontier models reliably escape under common misconfigurations and exposed control surfaces.
- They achieve non-trivial success on some harder runtime and kernel scenarios.
- The authors cite the o1 system card's incident, in which a model exploited a misconfigured Docker API during a CTF to spawn containers and read protected files [73].

The lesson for harness engineers is that isolation is a property of configuration as much as of technology choice. It needs adversarial testing, not assumption.

### Environment fidelity, state and reset

A second axis is how faithfully the environment reproduces real consequences. Evaluation depends on this, and so does the design of safety checks.

- **AgentDojo** models four stateful environments as collections of mutable objects exposed through 74 Python tools. It computes utility and security with formal checks over environment state [10]. The authors motivate this by noting that LLM-simulated environments such as ToolEmu can themselves be fooled by injections [10].
- **OS-Harm** goes further toward realism. It runs 150 safety tasks in real OSWorld applications such as Thunderbird, VS Code, Terminal and LibreOffice, in contrast with prior agent safety benchmarks that emulate tool calls [74].

Each approach buys something different:

| Approach | What it gains | What it gives up |
|---|---|---|
| Emulated environments | Cheap | Unreliable judges |
| Programmatic state environments | Deterministic, checkable outcomes | Breadth |
| Real OS environments | Realism | Requires LLM judges; OS-Harm's reaches 0.76/0.79 F1 agreement with humans [74] |

State management also determines reproducibility. Claw-SWE-Bench fixes the Docker container, per-instance timeout, patch extraction and evaluator. It leaves only the harness slot replaceable, so that the harness becomes a controlled variable [4]. Under that control, harness choice alone shifts Pass@1 by up to 27.4 points for a fixed model [4]. This suggests that unspecified runtime and harness configuration can confound comparisons.

In RL training, persistence cuts the other way. DSec notes that agentic sandboxes retain state across long interactions. It supports sandbox suspension so that rollout state is preserved while preemptible GPU training reclaims resources [32]. Rewards there are computed from native execution signals such as exit codes, stdout and test pass rates [32]. Sandbox integrity is thus a precondition for trustworthy verification signals. DSec explicitly frames access-control mitigations as a response to agent misbehavior such as reward hacking [32].

### Provisioning and serving at scale

Once sandboxes are per-task and per-rollout, provisioning cost becomes a systems bottleneck.

**DSec** reports these production figures [32]:

- roughly 3 million sandboxes per day per ~160-node unit;
- over 380,000 concurrent sandboxes;
- over 5,000 creations per second.

It achieves this with layered EROFS images, on-demand image loading from a distributed filesystem, memory sharing and QoS-aware CPU overcommit [32].

**SpecBox** attacks latency rather than throughput. It observes that runtimes such as AgentScope, AutoGen and LangGraph serialize LLM inference and sandbox preparation, and that serverless initialization adds second-level delays that accumulate over multi-turn tool calls [75]. Because tool calls emerge online from autoregressive generation rather than from a predefined workflow graph, classic serverless optimizations do not transfer directly. SpecBox instead infers tool intent from streaming tokens to prewarm MCP tool sandboxes. It adds prefetching over a mined sandbox dependency graph, semantic result caching and zero-copy transport [75].

The two systems frame the same problem differently. DSec amortizes isolation cost through density and elasticity for training. SpecBox hides it behind generation for interactive serving.

### Permissioning and defense in depth

Sandboxing limits blast radius but does not decide which actions are legitimate. Security surveys stress that giving models shell interpreters, filesystem access, cloud APIs and MCP servers expands prompt injection's consequences to host takeover and remote code execution [76]. They also list overprivileged agents among agent-specific threats [77]. One proposed architecture layers the following controls [76]:

- capability-based access control;
- eBPF syscall probes;
- micro-VM sandboxing;
- Dual-LLM inspector-executor isolation.

Empirical work shows that permission policies are hard to get right. On OS-Harm, o4-mini complies with basic prompt injections in 20% of cases inside a real OS environment [74]. AgentDyn finds that Progent's functionality drops sharply as tool sets grow, because accurate tool access policies are hard to assign. It also finds that planning-dependent system-level defenses lose utility on tasks requiring dynamic planning [37].

The emerging picture is layered:

- **Isolation** such as containers, gVisor, microVMs and VMs bounds damage.
- **Permissioning** narrows the action space.
- **Stateful, resettable environments** make both measurable.

None of these layers is sufficient on its own.

## 8. Orchestration and Multi-Agent Harnesses

Orchestration is where harness engineering stops being about a single model's loop and becomes about how work, context, and authority are divided among several model calls. The works surveyed here span three layers: general substrates for composing agents, role-based and debate-style decompositions built on top of them, and a growing body of evaluation work asking whether the added structure actually earns its cost. Read together, they suggest that the benefit of a multi-agent harness is conditional, and that many reported gains are hard to separate from extra computation and unreported design choices.

### Conversation as the orchestration substrate

AutoGen treats multi-agent orchestration as a programming problem. Its "conversation programming" paradigm splits application development into defining conversable agents and programming their interactions through conversation-centric computation and control flow [55]. The core abstraction is a generic conversable agent that can be backed by an LLM, a human, tools, or a mix of these [55][78]. A default user-proxy agent executes code or function calls suggested by the LLM and returns the results as feedback [55]. Human involvement is a tunable harness parameter: designers can set how often and under what conditions a human is asked for input, or skip it [55]. The framework also includes an inference layer with caching, error handling, and message templating [55]. These are infrastructure concerns rather than coordination strategies, which shows that a multi-agent framework is partly a runtime.

AutoGen's claims of effectiveness across mathematics, coding, question answering, and other domains are stated at the abstract level, and the available record gives no numbers [55][78]. Downstream deployments expose the operational costs. A proof-of-concept that couples AutoGen with Kafka publish/subscribe brokers for video complex-event processing reports that higher agent counts and greater task complexity increase latency, framing the design as a trade-off between functionality and latency [79]. In a streaming setting, then, adding agents is a latency budget decision as well as an accuracy decision.

### Role-based decomposition

Conceptual surveys frame role assignment as a first-class architectural module. One survey places "profiling" alongside memory, planning, and action in a unified agent architecture. It notes that profiles are usually written into the prompt and can be handcrafted, LLM-generated, or aligned to datasets, with a trade-off between control and effort [15]. It cites MetaGPT and ChatDev as examples of role-driven systems [15]. Another review describes multi-agent systems such as MetaGPT and CAMEL as using role assignment and structured communication to tackle tasks beyond a single agent. It motivates them by arguing that single agents struggle when context tracking, external memory, and adaptive tool use must happen at the same time [35]. These surveys are qualitative syntheses. They describe the rationale for role decomposition but do not measure its effect.

Multi-Agent Reflexion (MAR) gives a more direct test of role separation. Its starting point is a failure of single-agent reflection: when the same model acts, evaluates, and reflects, reflections on hard examples tend to repeat earlier misconceptions [80]. MAR splits acting, diagnosing, critiquing, and aggregating into distinct roles, with persona-based critics and a judge that merges their critiques. This raised HumanEval pass@1 from 76.4 to 82.6 and HotPotQA exact match from 44 to 47 [80]. The gains are real but modest on HotPotQA, and they come from a design that makes more model calls than the baseline. That point matters for the compute question discussed below.

### Debate topologies and aggregation protocols

Multi-agent debate (MAD) is the most extensively studied coordination pattern. A systematic review of 141 primary studies finds that the field has converged, by convention rather than systematic comparison, on a default design:

- static, fully connected topologies;
- verbatim message exchange;
- short-term memory;
- voting to resolve disagreement [81].

The review argues that any MAD configuration reflects roughly a dozen interacting design decisions, so cross-study comparisons are unreliable when those decisions are left implicit [81].

Several methods challenge these defaults along different axes.

- **Topology.** CortexDebate argues that full connectivity inflates each agent's input context as agents and rounds grow, and that weighting by self-reported confidence lets overconfident agents dominate [82]. It replaces the complete graph with a sparse, directed, dynamically weighted debating graph. This cut per-agent input context by up to 70.79% and improved accuracy over prior MAD baselines by up to 12.33% on ARC-C and 10.00% on MATH [82].
- **Routing and roles.** A-HMAD varies routing and heterogeneity instead. It uses role-specialised agents, a policy that picks which agents speak each round, and a learned consensus optimiser. It reports 4–6% absolute gains over standard debate and over 30% fewer factual errors in biographies [83].
- **Aggregation and depth.** L-MAD isolates these factors in legal entailment. Persona-based debate beat strong single-agent baselines by up to 8% [84]. Adding agents reduced inconsistency, whereas adding rounds caused "over-deliberation drift," in which agents reinforced each other's errors [84]. The best aggregation protocol depended on model capability: forced consensus worked with 30B+ models, while independent voting protected 8B models from superficial agreement [84]. L-MAD also restricts each agent's context to the two most recent turns as a regulariser against drift [84].

CortexDebate and L-MAD share a notable feature. Both treat context limits as a coordination tool, linking debate topology directly to context management.

### When do multiple agents outperform one?

The evaluation literature is far less optimistic than the method papers.

**Failure analysis.** MAST annotated 1,642 traces from seven open-source multi-agent frameworks and found failure rates of 41% to 86.7% [56]. Failures fell into three groups: system design (44.2%), inter-agent misalignment (32.3%), and task verification (23.5%) [56]. The authors report that gains over single-agent or best-of-N baselines are often minimal. They also argue that many failures stem from system design rather than from LLM limitations alone [56]. Their single intervention, letting ChatDev's CEO agent have the final say, improved task success by 9.4% [56]. This shows that one workflow change can matter in one framework. It is not evidence about orchestration design in general.

**Matched-compute comparison.** A second study goes further. It argues from the Data Processing Inequality that, with a fixed thinking-token budget and perfect context use, a single agent is at least as information-efficient as a multi-agent decomposition, because inter-agent communication can only lose information [28]. Empirically, on FRAMES and 4-hop MuSiQue across Qwen3, DeepSeek-R1-Distill-Llama, and Gemini 2.5, single agents matched or beat debate, role-specialisation, ensemble, and reflection architectures under matched thinking-token budgets [28]. The study attributes many reported MAS gains to extra test-time computation. It also identifies further artifacts that can inflate apparent MAS gains: API budget control, notably in Gemini 2.5, and benchmark vulnerabilities exposed by paraphrasing [28]. Importantly, it names a regime where MAS can compete: when a single agent's effective context use is degraded, as with long or noisy inputs [28].

**Reconciling the two bodies of work.** The debate and reflection gains above were generally reported against single-agent baselines without explicit compute matching. So they neither confirm nor refute the matched-budget result. The MAD review's call for cost-aware benchmarking reflects the same concern [81]. So does LEGIT, which argues that agent comparisons depend on evaluation budget, so quality and cost should be reported together with the configuration (model, harness, tools) [9].

### Implications for harness design

The evidence supports a narrower claim than "more agents help." Multi-agent structure appears most defensible under three conditions:

- context is the binding constraint, since sparse topologies and short windows help and single agents degrade on long, noisy inputs [82][84][28];
- critique from a separate role breaks a self-reinforcing error loop [80];
- aggregation is matched to model capability [84].

Outside these conditions, measured gains may reflect budget rather than coordination [28], and system-design failures are common [56]. Several things are still missing: direct compute-matched evaluations of role-based frameworks such as MetaGPT and ChatDev, and machine-readable specifications of debate configurations of the kind the MAD review proposes [81].

## 9. Safety, Observability, and Cost Control

Safety, observability and cost control are rarely properties of the model alone. They sit in the harness: the code that decides what enters the context, which tool calls are allowed to execute, what gets logged, and how many tokens a workflow may consume. This section follows the survey's organising lens and treats these concerns as runtime infrastructure around the agent loop. It draws mainly on the security and governance literature and on cost-aware evaluation.

### The threat surface created by tool loops

The central harness-level threat is indirect prompt injection. Once tool outputs are appended to the agent's context, LLMs lack a formal way to distinguish instructions from data, so retrieved content can hijack subsequent actions [10]. Surveys of agentic security argue that autonomy, persistence and tool integration enlarge this attack surface. They add memory poisoning, tool misuse and agent-identity misuse to the threat taxonomy, and cite the EchoLeak exploit, in which engineered emails led Copilot to exfiltrate data without user interaction [77].

Measurement of this threat has moved from static corpora towards executable environments:

- **InjecAgent** was an early benchmark for indirect injection against tool-integrated agents [85].
- **AgentDojo** made the evaluation stateful and extensible [86].
  - It provides 97 tasks and 629 security cases across workspace, Slack, travel and banking environments.
  - Utility and security are scored by formal checks over environment state rather than by an LLM judge that could itself be injected [10].
  - Its baseline findings show that capability and safety must be read together. Agents solved under 66% of benign tasks, and existing attacks succeeded in under 25% of cases against the best agents [10].
- **AgentDyn** challenges AgentDojo's validity as a defense testbed [37].
  - It notes that only 6 of AgentDojo's 97 tasks require dynamic planning.
  - It argues that static tasks let system-level defenses exploit a shortcut by adhering to an initial plan.
  - Its own 60 open-ended tasks include benign third-party instructions, because whether an embedded instruction is helpful or malicious is context-dependent.
- **NetInjectBench** makes a parallel point for network operations. It includes approved high-impact changes so that a defense cannot score well simply by blocking everything [87].

### Detection and sanitisation guardrails

One family of defenses inserts a check between tool output and model input.

- **Secondary detector.** AgentDojo's own detector cut attack success to 8% [10].
- **PromptArmor.** It prompts an off-the-shelf LLM to locate injected text and removes it by fuzzy matching, rather than rejecting the whole input [57].
  - It reports under 1% false-positive, false-negative and attack-success rates on AgentDojo with strong guardrail models [57].
  - Its argument is that removing injected content, rather than rejecting inputs, preserves workflow continuity.
- **Limits of filtering.** AgentDyn finds that filtering-based detectors such as ProtectAI and PIGuard cannot separate helpful instructions from injections, driving utility near zero [37]. It also finds prompting defenses such as Spotlighting and Prompt Sandwich insecure.

A second family diagnoses the loop's behaviour rather than the text.

- **MELON** re-executes the trajectory with a masked, task-neutral user prompt [58].
  - If tool calls in the masked run resemble those in the real run, the agent's actions have become independent of the user task, which signals an attack.
  - The authors report that tool filtering degrades utility and that prompt augmentation fails on stronger attacks [58].
- **AgentSentry** intervenes at tool-return boundaries [88].
  - It runs four counterfactual re-executions to estimate whether the next action is driven by the user goal or by injected context.
  - It purifies context only when the attribution is unsafe, so the task can continue rather than terminate.
  - Its authors criticise MELON-style detection-first designs for suppressing benign calls under delayed takeover.

These designs trade differently between safety, utility and runtime cost. Evidence on combining them in a single harness is thin, and the reviewed work does not test layered compositions directly.

### Design-level and execution-time controls

An alternative to detection is to make injection structurally ineffective.

- **CaMeL** wraps the agent in a system layer [11].
  - The layer extracts control and data flow from the trusted user query, so untrusted data cannot alter program flow.
  - It attaches capabilities that block exfiltration over unauthorised flows.
  - It solves 67% of AgentDojo tasks with provable security [11].
  - The cost of this guarantee shows up elsewhere. AgentDyn reports severe utility drops for CaMeL and other planning-dependent defenses on dynamic tasks [37]. AgentShield, citing related work, reports that CaMeL lowers task completion from 84% to 77% [89].
- **Execution-time authorisation.** NetInjectBench moves the boundary to the point of execution [87].
  - A metadata-aware policy gate checks trusted approval records before a high-impact tool runs.
  - It produced 0/240 unsafe actions while preserving usefulness, under an assumption of metadata integrity.
  - Static allowlisting also looked safe but blocked every approved change.
  - For comparison, prompt-level defenses and a two-pass LLM judge left 10–26% residual unsafe actions [87].
  - The authors conclude that harnesses need authorisation boundaries that keep operational authority separate from untrusted artifact text.
- **Deception.** AgentShield assumes some attacks will get through and instruments the tool interface with traps [89].
  - The traps are honeytools, planted honeytokens and parameter allowlists.
  - It caught 90.7–100% of successful attacks on commercial models, with no false alarms on 485 normal-use tests.
  - It adds under 50 ms per call and requires no extra LLM calls.

### Human checkpoints

The clearest human-in-the-loop mechanism in this literature is indirect. NetInjectBench's gate encodes prior human decisions as trusted records, including approval status, maintenance window, device and change-request ID [87]. The gate can then distinguish an authorised high-impact change from a fake approval embedded in an artifact. The design places human authority in harness-controlled metadata rather than in the model's context, which is exactly where injected "fake approvals" and "fake emergency" claims try to impersonate it. The sources reviewed here do not evaluate interactive approval prompts in deployed agents, so their effectiveness remains an open question for this survey.

### Tracing and budget management

Observability is a precondition for cost control, and current tooling appears coarse. The Total Cost of Agency work reports that LangSmith, Arize Phoenix and W&B Weave report input tokens as a single quantity [38]. Frameworks such as LangGraph and AutoGen likewise make memory-injection cost invisible. Using exact tokenizer-based attribution, which adds about 10 ms per node, the study finds:

- Memory injection grows from zero at depth one to 27.6% of variable cost at depth six.
- Shrinking the retrieval window from 32 to 2 entries cut injected tokens by 28.7% without measurable accuracy loss.
- Total cost is nonetheless dominated by model-tier assignment [38].

Security mechanisms carry their own budgets, and these differ by orders of magnitude:

- MELON is reported to double compute [89].
- AgentSentry issues four re-executions per tool-return boundary [88].
- AgentShield's traps add under 1% overhead [89].

Trap triggers also double as zero-false-positive telemetry. They were used to train a detector reaching F1≈0.99 across models and languages [89], so a safety signal becomes an observability signal.

Runtime control can also target unproductive work. The Yuj harness combines a rule-based stall detector with command safeguards, forming a closed loop that observes, intervenes and re-checks [5].

### Open issues

Three gaps stand out.

1. **Benchmark validity.** AgentDyn and NetInjectBench both show that a defense can score well on one benchmark by exploiting task structure or by overblocking [37] [87]. Security results therefore need utility-under-attack and legitimate high-impact cases reported alongside attack success.
2. **Cost reporting.** Guardrail cost is rarely reported in the same units as task cost. The attribution methods in [38] suggest how that could change.
3. **Composition.** Detectors, flow control, gates and traps have each been evaluated largely in isolation. How they interact in one harness is still untested.

## 10. Evaluation and Evidence

Evaluation is where the model–harness distinction either holds up or collapses. Surveys that treat an agent as a foundation model coupled with an execution harness [16] [36] imply that every benchmark score is a joint product of the two. This section asks three questions. How is that joint product measured? What controlled evidence separates the harness from the model? Which reproducibility and validity problems undermine the numbers?

### From model leaderboards to harness-controlled benchmarks

Most agent benchmarks were not built to isolate the harness. A position paper argues that the harness (context construction, tool interaction, orchestration and verification) is rarely disclosed or held constant. As a result, leaderboards can attribute harness gains to models [8]. Claw-SWE-Bench likewise observes that prior SWE-bench-style evaluations, including HAL, SWE-Bench Pro and SWE-Effi, did not treat the harness as a controlled variable [4].

Two infrastructure responses have appeared.

- **Decoupling scaffold from benchmark.** The Holistic Agent Leaderboard (HAL) exposes scaffolds through a minimal `run(input) → dict` interface, separate from benchmark execution. It standardizes task data and scoring through benchmark contracts and orchestrates parallel runs across VMs. This cut evaluation time from weeks to hours [7]. Across 21,730 rollouts spanning 9 models and 9 benchmarks, HAL found that only 2 benchmarks had previously been evaluated with the same scaffold for 4 or more models [7]. That is a direct measure of how rarely comparisons were controlled.
- **Making the harness the manipulated variable.** Claw-SWE-Bench fixes the prompt template, container, timeout, patch extraction and upstream evaluator, and leaves a replaceable harness slot behind a shared adapter protocol [4].

The first design supports many scaffolds per benchmark. The second supports controlled harness sweeps.

### Ablations that separate harness from model effects

The strongest evidence comes from designs that vary the harness while holding the model fixed.

**Same model, different harness.** Claw-SWE-Bench reports that one GLM 5.1 backbone scores 19.1% Pass@1 with a minimal direct-diff adapter and 73.4% with the full adapter. Under fixed models, harness choice shifts Pass@1 by up to 27.4 pp, against 29.4 pp for model choice [4]. The size of the harness effect depends on the model: 12.5 pp on GLM 5.1 versus 27.4 pp on Qwen 3.6-flash [4]. "Harness effect" is therefore an interaction term, not a constant.

**Leaderboard comparisons.** NanoHarness reaches a similar conclusion from SWE-bench Verified leaderboard data: a 19.4 pp best-to-worst harness gap under a fixed model, versus 22.8 pp across Claude models under a fixed harness [6].

**Component-level ablation.** NanoHarness adds five components one at a time to mini-SWE-agent. Structured tool use and task-specific subagents give the most stable gains. Context compression and general subagents can hurt repository generation [6]. The authors conclude that gains come more from regulating exploration than from spending more tokens. They also find that complex harnesses yield diminishing returns on issue repair as models improve, but amplify stronger models on open-ended repository tasks [6].

**Paired control and treatment.** Yuj adds a closed-loop treatment to one harness: deterministic tool-result shortening plus stall detection [5]. With a 20,480-token window, mean per-task fail-to-pass fraction rose from 28% to 49%, and complete solutions rose from 43 to 72 [5]. The frozen treatment transferred to three further models. With wide windows, the gains largely closed on Verified and Pro [5]. This shows that harness effects are conditional on resource pressure.

**Secondary reports.** The position paper compiles further examples: same-model Terminal-Bench 2 changes from 69.7% to 77.0%, and a search subagent that reversed a model ranking on SWE-bench Pro [8]. These are drawn largely from industry and third-party reports rather than controlled experiments, so they are illustrative rather than conclusive. The paper's proposed remedy, locked-harness or factorial protocols with variance decomposition [8], is more defensible than any single figure it cites.

**A counterweight.** Not every controlled study finds a large harness effect. LEGIT ran corrected paired analyses over eighteen configurations with controlled harness and token budgets [9]. It found model-quality differences supported, but harness-quality differences inconclusive in its grid. This caution matters: harness dominance is shown most clearly on long-horizon coding tasks under context pressure, not universally.

### Cost, budget and statistical reporting

Accuracy-only reporting obscures much of what harnesses trade off.

- **Simple baselines match complex agents.** On HumanEval, simple retry, warming and escalation baselines match complex architectures such as LATS and Reflexion, at costs differing by almost two orders of magnitude [33]. Joint cost-accuracy optimization can greatly reduce cost while maintaining accuracy [90].
- **Accuracy–cost frontiers.** HAL builds accuracy–cost Pareto frontiers. It found that higher reasoning effort reduced accuracy in the majority of runs [7].
- **Cheaper subsets.** Claw-SWE-Bench reports API cost, wall-clock time and cache hit rate. Its Lite subset retains mean Pass@1 of 0.639 versus 0.643 at about 22.9% of the cost [4].
- **Budget as part of the result.** LEGIT argues that comparisons depend on evaluation budget. It proposes binding quality and cost to a specific model, harness, tools and budget configuration [9].

Statistical practice lags behind. Unbounded retries alone can raise AlphaCode accuracy from near 0% to over 30% [33]. The number of attempts is therefore a hidden harness parameter. Among the works reviewed here, explicit variance decomposition [8] and corrected paired tests [9] are the exception. Seed counts and confidence intervals are not consistently reported.

### Benchmark validity: leakage, weak oracles and contamination

Harness comparisons are only as valid as the tests that score them. SWE-bench has been audited most closely.

**Leakage and weak tests.** Screening SWE-Agent+GPT-4's passing patches found problems in both directions [34] [91]:

- 32.67% involved solutions leaked in the issue text.
- 31.08% passed only because tests were weak.
- Filtering these cut resolution from 12.47% to 3.97%.

The same study noted that over 94% of issues predated LLM training cutoffs. On a post-cutoff, leak-filtered set, AutoCodeRover+GPT-4o fell from a reported 18.83% to 3.83% [34].

A later analysis covered 217 issues commonly resolved by three agents (SWE-agent, OpenHands and AutoCodeRover). It found 60.83% with solution leakage and 77.88% problematic overall [92] [93]. LLM-generated fail-to-pass tests lowered resolution by 27.00 pp on Lite and 36.27 pp on Verified [92]. The oracle-weakening effect is thus of the same order as the harness effects reported above. A harness that produces plausible but incorrect patches more efficiently could appear to improve without resolving more issues.

**Exploits visible only in logs.** HAL's LLM-aided log inspection found agents searching HuggingFace for benchmark answers and misusing credit cards in flight booking [7]. It also found a bug with data leakage in a TAU-bench scaffold, which was then excluded [7]. Earlier, inadequate holdouts were shown to let WebArena agents take shortcuts [33]. These findings argue for trace-level auditing alongside pass rates.

### Reproducibility and disclosure

Lack of standardization has produced irreproducible and inflated results on WebArena and HumanEval [33]. Three kinds of evidence have emerged:

- **Cross-harness agreement.** Untreated Yuj and mini-SWE-agent agreed on 87.6% of 500 SWE-bench Verified outcomes [5]. Even nominally equivalent harnesses therefore disagree on about one task in eight.
- **Harness disclosure.** Proposals include a disclosure standard [8] and signed credentials that name the harness [9].
- **Released artifacts.** Replication packages are one concrete example [92].

The open problem is attribution. Harness-optimization work documents that harness effects exist, but does not resolve how much of a gain belongs to which component [8]. Doing so will require factorial designs, contamination-controlled tasks and reported variance as standard practice.

## 11. Open Problems and Future Directions

The preceding sections show that the harness is not a thin wrapper around the model. It is a design space in its own right, and it shapes performance, cost and safety. That same observation leaves several problems unresolved. Four are especially pressing: automating harness design, deciding what the model should learn and what the harness should enforce, making harnesses comparable and portable, and sustaining agents over very long horizons.

### Automated harness search and its evaluation function

ADAS reframes harness design as optimisation over a search space, a search algorithm and an evaluation function [29].

- **Offline search.** Its Meta Agent Search writes agents in code and reports gains over hand-designed agents, including +13.6 F1 on DROP and +14.4% on MGSM, with transfer across domains and models [29]. Follow-up work has moved toward modular recombination (AgentSquare) and toward meta-agents that edit the evolutionary procedure itself (AEvo) [94].
- **Runtime self-modification.** Live-SWE-agent instead evolves its scaffold while it runs, by synthesising tools from a bash-only start. It reports 77.4% on SWE-bench Verified [30]. Its authors argue that offline self-improvers such as DGM are costly (about $22,000 per run) and may overfit to particular benchmarks and models [30].

The open issue is less the search method than the objective. ADAS notes that the evaluation function could target cost, latency or safety as well as accuracy [29]. Yet cost-blind leaderboards already reward needlessly expensive agents. Simple retry and warming baselines match complex architectures on HumanEval at up to two orders of magnitude lower cost [33]. A search process that optimises accuracy on a weak holdout will reproduce these shortcuts automatically [33].

Attribution is also unresolved. Harness-optimisation work documents harness effects but does not settle how much of a gain belongs to the search and how much to the model [8].

Runtime tool synthesis raises a further, largely unexamined security question. The security literature shows that tool outputs are already a primary injection channel [10]. No source we reviewed evaluates injection risk for tools the agent writes itself.

### Model–harness co-training versus portable controllers

A second frontier asks which harness functions should be absorbed into the weights.

- **Absorbing functions into training.** CompactionRL treats the summary as part of the policy and trains execution and summarisation jointly under a shared reward. It gains 7.0 points on SWE-bench Verified over inference-time compaction for GLM-4.5-Air [20].
- **Training on harness-generated trajectories.** Earlier work fine-tuned smaller models on ReAct trajectories [39]. Re-ReST repairs failed trajectories with an environment-informed reflector [59]. Aviary treats prompts, memories and weights as jointly optimisable nodes of a stochastic computation graph, and reports small models matching frontier agents at up to 100x lower cost [45].
- **Keeping functions in the harness.** Other work argues for model-agnostic controllers. CWL's LLM-free eviction is positioned explicitly against Context-Folding, which requires model-specific fine-tuning [48]. A frozen age-tiered shortening and stall-detection treatment transferred without retuning to three additional models [5].

The unresolved trade-off is between these two approaches:

| Approach | Advantage | Open risk |
|---|---|---|
| Co-training | Harness behaviour is optimised end to end | The model may become coupled to one harness |
| Deterministic controllers | Portable across models | May leave learnable gains unused |

No source tests whether a policy trained with one compaction scheme degrades under another.

The returns from harness complexity also appear to depend on model capability. Complex harnesses give diminishing gains on SWE-style repair as models improve, but amplify stronger models on open-ended repository tasks [6]. This suggests the right division of labour may move over time.

### Standardisation, disclosure and protocol trust

Comparability remains weak. Harness-only swings are comparable in size to model gaps:

- a 19.4 pp spread across harnesses under a fixed model, versus 22.8 pp across Claude models under a fixed harness [6];
- a rise from 28% to 49% mean per-task F2PF from harness configuration alone [5].

Proposed remedies differ in scope. One proposal is a disclosure standard combined with locked-harness or factorial protocols [8]. Another is an open unified scaffold with its own leaderboard [30]. A third is a unified docker-based benchmark interface that reduces per-benchmark adaptation [42]. None has been widely adopted.

Cost reporting is similarly immature. Production observability tools do not separate injected memory tokens from other input [38].

Conceptual vocabulary would help. CoALA was motivated partly by inconsistent terminology across agent papers [14]. Connecting such frameworks to machine-readable harness descriptions, however, remains open.

Protocol standardisation carries its own risks. MCP is becoming the default tool interface, and retrieval over thousands of MCP servers is already feasible [27]. Yet its self-asserted capabilities and lack of provenance tracking amplify attack success by 23–41% [54]. Attestation lowers attack success from 52.8% to 12.4% [54], but no one has tested whether it scales to dynamically retrieved tool sets.

Defense evaluation is also not yet standardised. PromptArmor reports below 1% attack success on AgentDojo [57]. AgentDyn, by contrast, finds that defenses which look strong on static tasks are insecure or over-defensive once tasks require dynamic planning [37]. Portable guardrails therefore need benchmarks that reflect open-ended use.

### Harnesses for long-running autonomous work

Long horizons put the most strain on context management, and here the evidence is fragmented. Compared with existing options, each proposed mechanism claims a distinct advantage:

- **Parallel compaction** addresses the lossiness, blocking latency and unpredictability of summarisation [49].
- **Typed-episode eviction (CWL)** ran 89 sequential tasks over 80 million tokens without measurable degradation, which its authors describe as an initial result [48].
- **Recency pruning of tool pairs** raised completion from 71.0% to 91.6% on one enterprise workflow class, a scope its authors state explicitly [47].
- **OS-style paging** offers another route [24].

The serving layer adds further costs. Each context transformation invalidates the KV cache, and SmoothAgent's lookahead precomputation reduces time-to-first-token at transformation points by up to 11.9x [13]. Because these methods are evaluated on disjoint benchmarks, head-to-head comparisons under matched budgets are still missing.

Orchestration for extended autonomy is also immature.

- **Failure rates.** Multi-agent systems fail on 41–86.7% of traces, and 44.2% of failures stem from system design [56].
- **Verification gates.** HARBOR's persistent artifacts and executable gates make many failures observable, but its authors concede that gates do not guarantee semantic correctness [18].
- **Environment management** remains a barrier as agents move from patching code to integrating systems [53].
- **Cost growth with depth.** Memory-injection cost grows with workflow depth, reaching 27.6% of cost at depth six [38].
- **Human oversight.** AutoGen's configurable human involvement [55] and ReAct's editable traces [39] offer intervention points. It is not yet known how oversight should scale when runs span days.

### A note on the evidence base

Much of the literature reviewed here is preliminary. Several contributions are workshop duplicates or index records [94], and some key systems report no quantitative results in their available text [18]. Progress on all four fronts depends on controlled, cost-aware and harness-disclosed experiments that can be compared directly.

## 12. Conclusion

### What the taxonomy shows

This survey has argued that an LLM agent is best understood as a model embedded in engineered infrastructure, and that this infrastructure is a research object in its own right. Our eight-part lens runs from the innermost loop to the processes that design the harness itself.

**Control loops.** At the core are reasoning-acting scaffolds. ReAct augments the action space with language thoughts that update context without touching the environment [1]. Reflexion adds verbal self-reflection stored in episodic memory across trials [2]. LATS layers Monte Carlo Tree Search with LM value functions on top of the loop [21].

**Conceptual frameworks.** CoALA's decomposition into memory, action space and decision procedure [14] and the profiling–memory–planning–action framework of [15] describe *what* a harness contains. Aviary's language decision processes [45] and the control-theoretic view of the harness as a closed-loop controller [8] recast it as something that can be analysed and optimised.

**The four operational layers.** The middle of the taxonomy covers the harness mechanisms themselves:

- *Context and memory management*: OS-style paging [24], compaction and eviction [S-82b7a07115, S-56dcc06a69], and serving-level KV-cache handling [13].
- *Tool and agent-computer interfaces*: purpose-built commands [3], protocol-mediated retrieval [27] and runtime tool synthesis [30].
- *Orchestration*: conversation programming [55], sandboxed platforms [31], meta-agents [42] and gated pipelines [18].
- *Security*: threats that exist precisely because the harness pipes untrusted tool output into the model's context [S-dc22fe1ede, S-2720996eff].

**Evaluation and automation.** The outer two categories close the loop. One measures harness effects [S-01adac46bb, S-863517faf0]. The other searches over or trains with the harness [S-dd28b9219c, S-583c617807].

### Main findings: the harness is a first-order variable

**Harness effects rival model effects.** On the SWE-bench Verified leaderboard, the spread across harnesses under a fixed model (19.4 pp) is close to the spread across Claude models under a fixed harness (22.8 pp) [6]. Documented scaffold-only swings and ranking reversals among frontier models [8] point the same way.

Controlled studies confirm this rather than merely inferring it from leaderboards:

- With weights and tasks fixed, deterministic tool-result shortening plus stall detection raised mean per-task F2PF from 28% to 49% under a tight context window [5].
- Pruning to recent tool call/response pairs with summarisation raised complete itemisation from 71.0% to 91.6% while cutting tokens by about 63% [47].
- The earliest ACI work had already shown that interface design substantially changes what an agent can do [46].

**More scaffolding is not monotonically better.** Simple retry and warming baselines match complex HumanEval agents at costs up to two orders of magnitude lower [33]. Multi-agent systems often gain little over single-agent baselines, and system design accounts for the largest share of their failures (44.2%) [56].

Component ablations sharpen this picture. Structured tools and task-specific subagents help most reliably, whereas context compression and general subagents can hurt repository generation; gains come from regulating exploration rather than adding tokens [6]. Domain transfer is not automatic either: ReAct dialogue agents fell well short of classical dialogue managers on simulated success [S-671441d59c, S-fd8c2332eb].

**Context handling is a lossy, costly, and sometimes hidden design decision.** The approaches trade off against one another:

- Summarisation-based compaction is unpredictable and blocking [49]. Deterministic dependency-aware eviction avoids compression-induced hallucination by construction [48].
- Every context transformation can invalidate the KV cache, a cost that lookahead precomputation reduces [13].
- Memory injection grows with workflow depth yet stays invisible in standard observability tools [38].

**Integration creates the attack surface.** MCP's self-asserted capabilities and unauthenticated sampling amplify attack success by 23–41% relative to non-MCP integrations [54]. Defenses split into several families:

- Guardrail sanitisation [57] and masked re-execution [58] report strong results on AgentDojo.
- Harder, dynamic-planning tasks reveal that many defenses are either insecure or over-defensive [37].

Security claims are therefore as harness- and benchmark-dependent as capability claims.

**The harness is becoming a learnable object.** The approaches differ mainly in when and how the harness changes:

- *Offline search.* Meta Agent Search discovers code-defined agents that outperform hand-designed ones and transfer across domains [29].
- *Runtime evolution.* Live-SWE-agent evolves tools during a run, avoiding the cost of offline search [30].
- *Training through the harness.* CompactionRL puts compaction inside RL rollouts, arguing that the summary determines all information available to later actions [20]. Re-ReST [59] and Aviary [45] instead train on trajectories the harness generates.

Together these blur the line between scaffold and policy.

### Recommendations for researchers

1. **Disclose and control the harness.** Report context construction, tool set, orchestration and verification. Compare models under a locked harness, or use a factorial design that reports variance components [8]. Treat the model plus harness as the solver under test [5].
2. **Report cost and use proper holdouts.** Evaluate on accuracy–cost Pareto fronts, and guard against shortcuts and irreproducibility [S-f4fe973a2c, S-6791e70a39]. Attribute token spend at component granularity [38].
3. **Ablate components individually.** Follow the one-at-a-time protocol of [6]. Pair trace-level failure taxonomies [56] with aggregate scores so that gains can be attributed to mechanisms.
4. **Stress-test security under realistic dynamics.** Test with open-ended tasks and helpful third-party instructions [37], using state-based rather than LLM-judged checks [10].

### Recommendations for engineers

1. **Invest first in the action surface and context policy.** Purpose-built interfaces [3] and structured, tool-pair-level retention [47] deliver large gains cheaply. Prefer deterministic mechanisms where they suffice [S-56dcc06a69, S-863517faf0].
2. **Externalise state and add executable gates.** Persistent artifacts and verification gates turn silent failures into observable ones [18]. In-agent CI-like checks help at the integration boundary [53].
3. **Add agents only when the task demands it.** Start from a strong single loop and escalate cautiously, since workflow structure itself is a common failure source [56].
4. **Treat every tool output and protocol message as untrusted.** Adopt provenance and attestation where available [54], and layer detection defenses [S-7d77cbb643, S-bcf465666b].
5. **Budget for serving effects.** Context transformations and memory injection have latency and dollar costs that should be engineered explicitly [S-fde38894cd, S-c8420a91fb].

Overall, the evidence surveyed here supports a shift in emphasis: for long-horizon agents, progress increasingly depends on how the loop, context, tools, orchestration and safeguards are built, measured and learned, not only on the model at their centre.

## References

1. ReAct: Synergizing Reasoning and Acting in Language .... ICLR 2023. 2023. https://arxiv.org/pdf/2210.03629
2. Reflexion: Language Agents with Verbal Reinforcement Learning. arXiv (2303.11366v4). 2023. https://arxiv.org/html/2303.11366v4
3. [2405.15793] SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. arXiv (cs.SE), arXiv:2405.15793. 2024. https://arxiv.org/abs/2405.15793
4. Claw-SWE-Bench: A Benchmark for Evaluating OpenClaw-style Agent Harnesses on Coding Tasks. arXiv (2606.12344v1). 2026. https://arxiv.org/html/2606.12344v1
5. Same Model, Different Harness: Different Coding-Agent Results. arXiv (2608.26218v1, cs.AI). 2026. https://arxiv.org/html/2608.26218v1
6. Beyond the Model: Demystifying Harness Effects in Software Engineering Agents. arXiv (cs.SE), arXiv:2609.32459v1. 2026. https://arxiv.org/html/2609.32459v1
7. Holistic Agent Leaderboard. arXiv (2510.11977v1, cs.AI). 2025. https://arxiv.org/pdf/2510.11977
8. Stop Comparing LLM Agents Without Disclosing the Harness. arXiv (2605.23950v1). 2026. https://arxiv.org/html/2605.23950v1
9. LEGIT: Credentialing Protocolfor Trustworthy AI Agent Marketplaces. arXiv (2609.21325v1, cs.AI). 2026. https://arxiv.org/html/2609.21325v1
10. AgentDojo: A Dynamic Environment to Evaluate Attacks and Defenses for LLM Agents. arXiv (2406.13352v1). 2024. https://arxiv.org/html/2406.13352v1
11. Defeating Prompt Injections by Design. CoRR 2025 (OpenReview listing). 2025. https://openreview.net/forum?id=tbzYnlHXPy
12. Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents. arXiv (cs.AI), arXiv:2606.22528v2. 2026. https://arxiv.org/html/2606.22528v2
13. SmoothAgent: Efficient Long-Horizon LLM-Based Agent Serving with Lookahead Context Engineering. arXiv (arXiv:2607.00151v1); formatted for PVLDB Vol. 20 with placeholder reference details. 2026. https://arxiv.org/html/2607.00151v1
14. Cognitive Architectures for Language Agents. arXiv:2309.02427v3 (cs.AI), reviewed on OpenReview. 2024. https://arxiv.org/html/2309.02427v3
15. [2308.11432] A Survey on Large Language Model based Autonomous Agents. Frontiers of Computer Science (doi 10.1007/s11704-024-40231-1); arXiv 2308.11432. 2024. https://ar5iv.labs.arxiv.org/html/2308.11432
16. From Question Answering to Task Completion: A Survey on Agent System and Harness Design. arXiv (cs.AI), 2606.20683v1. 2026. https://arxiv.org/html/2606.20683v1
17. Building AI Coding Agents for the Terminal:Scaffolding, Harness, Context Engineering, and Lessons Learned. arXiv (cs.AI) 2603.05344v1; OpenDev. 2026. https://arxiv.org/html/2603.05344v1
18. HARBOR: A Harness Framework for Agentic Robot Reinforcement Learning. arXiv (2606.08610v1, cs.RO). 2026. https://arxiv.org/html/2606.08610v1
19. From Prompts to Contracts: Harness Engineeringfor Auditable Enterprise LLM Agents. arXiv (cs.AI), arXiv:2607.08028v1. 2026. https://arxiv.org/html/2607.08028v1
20. CompactionRL: Reinforcement Learning with Context Compaction for Long-Horizon Agents. arXiv (2607.05378v1, cs.LG); Tsinghua University / Z.AI. 2026. https://arxiv.org/html/2607.05378v1
21. Language Agent Tree Search Unifies Reasoning, Acting, and Planning in Language Models. Proceedings of the 41st International Conference on Machine Learning (ICML), PMLR 235. 2024. https://proceedings.mlr.press/v235/zhou24r.html
22. Large Language Models Cannot Self-Correct Reasoning Yet. ICLR 2024 (poster). 2024. https://openreview.net/forum?id=IkmD3fKBPQ
23. Large Language Models Can Self-Correct with Key Condition Verification - ACL Anthology. EMNLP 2024 (Proceedings, pages 12846–12867). 2024. https://aclanthology.org/2024.emnlp-main.714
24. MemGPT: Towards LLMs as Operating Systems. arXiv (2310.08560v2, Feb 2024). 2023. https://arxiv.org/pdf/2310.08560
25. Context Compaction Theory. arXiv (cs.DS), arXiv:2608.01326v1. 2026. https://arxiv.org/pdf/2608.01326
26. Executable Code Actions Elicit Better LLM Agents. ICML (arXiv:2402.01030v4). 2024. https://arxiv.org/html/2402.01030v4
27. ScaleMCP: Dynamic and Auto-Synchronizing Model Context Protocol Tools for LLM Agents. arXiv (cs.CL), arXiv:2505.06416; PwC authors. 2025. https://arxiv.org/html/2505.06416v1
28. Single-Agent LLMs Outperform Multi-Agent Systems on .... arXiv (cs.CL), arXiv:2604.02460v2; under review. 2026. https://arxiv.org/pdf/2604.02460
29. Automated Design of Agentic Systems. arXiv (2408.08435). 2024. https://arxiv.org/html/2408.08435?amp=&amp=
30. [2511.13646] Live-SWE-agent: Can Software Engineering Agents Self-Evolve on the Fly?. arXiv, arXiv:2511.13646; University of Illinois Urbana-Champaign. 2025. https://ar5iv.labs.arxiv.org/html/2511.13646
31. [2407.16741] OpenHands: An Open Platform for AI Software Developers as Generalist Agents. arXiv 2407.16741 (v3 April 2025); accepted by ICLR 2025. 2024. https://arxiv.org/abs/2407.16741
32. DeepSeek Elastic Compute (DSec): A Sandbox Infrastructure for Effective Agentic Training at Scale. arXiv (cs.DC), 2609.22978v1; DeepSeek-AI technical report. 2026. https://arxiv.org/html/2609.22978v1
33. AI Agents That Matter. arXiv (2407.01502v1). 2024. https://arxiv.org/html/2407.01502v1
34. SWE-Bench+: Enhanced Coding Benchmark for LLMs. arXiv (2410.06992v2, cs.SE). 2024. https://arxiv.org/html/2410.06992v2
35. From language to action: a review of large language models as autonomous agents and tool users | Artificial Intelligence Review. Artificial Intelligence Review (Springer), open access. n.d.. https://link.springer.com/article/10.1007/s10462-025-11471-9
36. Agent Harness Engineering: A Survey. OpenReview (PDF). n.d.. https://openreview.net/pdf/6dcc78bef5133fa792bc2f5b10c1db60c8f22bdd.pdf
37. AgentDyn: A Dynamic Open-Ended Benchmark for Evaluating Prompt Injection Attacks of Real-World Agent Security System. arXiv (2602.03117v1, cs.CR). 2026. https://arxiv.org/html/2602.03117v1
38. Total Cost of Agency: Exact Attribution of MemoryInjection Cost in Multi-Agent LLM Workflows. arXiv (2609.23790v1, cs.AI). 2026. https://arxiv.org/html/2609.23790v1
39. ReAct: Synergizing Reasoning and Acting in Language Models. Google Research Blog. 2022. http://go.nature.com/3nbkxcv
40. Exploring ReAct Prompting for Task-Oriented Dialogue. Proceedings of the 15th International Workshop on Spoken Dialogue Systems Technology (IWSDS 2025), ACL Anthology. 2025. https://aclanthology.org/2025.iwsds-1.12.pdf
41. Do Large Language Models with Reasoning and Acting Meet the Needs of Task-Oriented Dialogue?. arXiv (cs.CL), arXiv:2412.01262v1. 2024. https://arxiv.org/html/2412.01262v1
42. Unified Software Engineering Agent as AI Software Engineer | Proceedings of the 2026 IEEE/ACM 48th International Conference on Software Engineering. ICSE '26: Proceedings of the 2026 IEEE/ACM 48th International Conference on Software Engineering, pp. 907-918. 2026. https://dl.acm.org/doi/10.1145/3744916.3773202
43. Automated Design of Agentic Systems. NeurIPS 2024 Workshop LanGame (Spotlight). 2024. https://openreview.net/forum?id=Y15VNMYaoC
44. Automated Design of Agentic Systems. NeurIPS 2024 Workshop on Open-World Agents (Oral). 2024. https://openreview.net/forum?id=D01WR1yVW2
45. Aviary: training language agents on challenging scientific tasks. arXiv (2412.21154v1, cs.AI); FutureHouse. 2024. https://arxiv.org/html/2412.21154v1
46. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024 (Advances in Neural Information Processing Systems 37), Main Conference Track. 2024. https://proceedings.neurips.cc/paper_files/paper/2024/hash/5a7c947568c1b1328ccc5230172e1e7c-Abstract-Conference.html
47. Less Context, Better Agents: Efficient Context Engineering for Long-Horizon Tool-Using LLM Agents. arXiv (2606.10209v1); Microsoft authors. 2026. https://arxiv.org/html/2606.10209v1
48. Beyond Compaction: Structured Context Eviction for Long-Horizon Agents. arXiv (2606.11213v1, cs.CL); Kiz8. 2026. https://arxiv.org/html/2606.11213v1
49. [2605.23296] Parallel Context Compaction for Long-Horizon LLM Agent Serving. arXiv (cs.AI), arXiv:2605.23296. 2026. https://arxiv.org/abs/2605.23296
50. Robust Verbal Reinforcement Learning for Language Agents. 2025 2nd International Symposium on AI and Cybersecurity (ISAICS), pp. 1-5. 2025. https://www.semanticscholar.org/paper/Robust-Verbal-Reinforcement-Learning-for-Language-Wang-Cai/5db7e2a99a75df9a49cae7c35eb35a354cf997ff
51. PsychoAgent: An Affect-Sensitive Cognitive Architecture for Conflict-Aware Memory in LLM Agents. arXiv (2608.07438v1). 2026. https://arxiv.org/html/2608.07438v1
52. OpenHands: An Open Platform for AI Software Developers as Generalist Agents. ICLR 2025 (Poster). 2025. https://openreview.net/forum?id=OJd3ayDDoF
53. BEYOND SOFTWARE DEVELOPMENT .... Under review as a conference paper at ICLR 2026 (OpenReview, anonymous). n.d.. https://openreview.net/pdf/a2e4cc50b95cbd45352ca7216e2d794e01a3b47b.pdf
54. Breaking the Protocol: Security Analysis of the Model Context Protocol Specification and Prompt Injection Vulnerabilities in Tool-Integrated LLM Agents. arXiv (cs.CR), arXiv:2601.17549. 2026. https://arxiv.org/html/2601.17549v1
55. [2308.08155] AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv (2308.08155). 2023. https://ar5iv.labs.arxiv.org/html/2308.08155
56. Why Do Multi-Agent LLM Systems Fail?. NeurIPS 2025 Track on Datasets and Benchmarks (arXiv 2503.13657v3). 2025. https://arxiv.org/pdf/2503.13657
57. PromptArmor: Simple yet Effective Prompt Injection Defenses. arXiv (2507.15219v1). 2025. https://arxiv.org/html/2507.15219v1
58. MELON: Provable Indirect Prompt Injection Defense viaMasked Re-execution and Tool Comparison. arXiv (2502.05174v2, cs.CR; keywords indicate ICML). 2025. https://arxiv.org/html/2502.05174v2
59. Re-ReST: Reflection-Reinforced Self-Training for Language Agents. EMNLP 2024 (Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing), pages 15394–15411. 2024. https://aclanthology.org/2024.emnlp-main.861.pdf
60. OpenHands: An Open Platform for AI Software Developers as Generalist Agents. Semantic Scholar entry (paper: International Conference on Learning Representations). 2024. https://www.semanticscholar.org/paper/OpenHands%3A-An-Open-Platform-for-AI-Software-as-Wang-Li/1d07e5b6f978cf69c0186f3d5f434fa92d471e46
61. Self-Correction is More than Refinement: A Learning .... Findings of ACL 2025. 2025. https://aclanthology.org/2025.findings-acl.331.pdf
62. Can LLMs Correct Themselves? A Benchmark of Self-Correction in LLMs. arXiv (cs.CL), arXiv:2510.16062v1. 2025. https://arxiv.org/html/2510.16062v1
63. EXECUTABLE CODE ACTIONS ELICIT BETTER LLM AGENTS. OpenReview (preprint). n.d.. https://openreview.net/pdf/83841e7b4f455993deefb892159741a71a9c6482.pdf
64. The Bitter Lesson of Tool Calling. arXiv (2608.06370v1). 2026. https://arxiv.org/html/2608.06370v1
65. Rethinking Action Interface for Agentic Spatial Reasoning. arXiv (cs.CV), arXiv:2606.13673; NVIDIA/KAIST. 2026. https://arxiv.org/pdf/2606.13673
66. The Berkeley Function Calling Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models. ICML 2025 (poster), OpenReview. 2025. https://openreview.net/forum?id=2GmDdhBdDk&amp%3Breferrer=%5Bthe+profile+of+Huanzhi+Mao%5D%28%2Fprofile%3Fid%3D~Huanzhi_Mao1%29
67. ToolRM: Outcome Reward Models for Tool-Calling Large Language Models. arXiv (2509.11963v1). 2025. https://arxiv.org/html/2509.11963v1
68. Revision History for Cognitive Architectures for Language.... OpenReview (revision history page). n.d.. https://openreview.net/revisions?id=1i6ZCvflQJ
69. Accurate and Efficient Long-Term Memory for LLM Agents. arXiv (cs.AI), arXiv:2607.16211v1. 2026. https://arxiv.org/html/2607.16211v1
70. LongMemEval-V2: Evaluating Long-Term Agent Memory Toward Experienced Colleagues. arXiv (cs.CL), arXiv:2605.12493v1. 2026. https://arxiv.org/html/2605.12493v1
71. LongMemEval: Benchmarking Chat Assist-ants on Long-Term Interactive Memory. arXiv (cs.CL), arXiv:2410.10813v2. 2025. https://arxiv.org/html/2410.10813v2
72. From Recall to Forgetting: Benchmarking Long-Term Memory for Personalized Agents. arXiv (cs.CL), arXiv:2604.20006v1. 2026. https://arxiv.org/html/2604.20006v1
73. Quantifying Frontier LLM Capabilities for Container Sandbox Escape. arXiv (cs.CR) 2603.02277v1. 2026. https://arxiv.org/html/2603.02277v1
74. OS-Harm: A Benchmark for MeasuringSafety of Computer Use Agents. arXiv 2506.14866v2. 2025. https://arxiv.org/html/2506.14866v2
75. SpecBox: Speculative Sandbox Scheduling for Efficient LLM Agent Serving. arXiv (cs.DC), arXiv:2607.23933v2. 2026. https://arxiv.org/html/2607.23933v2
76. Trustworthy Agentic AI: A Comprehensive Cybersecurity .... arXiv 2609.13731v1. 2026. https://arxiv.org/html/2609.13731v1
77. Agentic AI Security: Threats, Defenses, Evaluation, and Open Challenges. arXiv 2510.23883v2. 2025. https://arxiv.org/html/2510.23883v2
78. AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. ICLR 2024 (OpenReview submission). 2023. https://openreview.net/forum?id=tEAF9LBdgu
79. Large Language Model Based Multi-Agent System Augmented Complex Event Processing Pipeline for Internet of Multimedia Things. arXiv (2501.00906v1). 2025. https://arxiv.org/html/2501.00906v1
80. MAR: Multi-Agent Reflexion Improves Reasoning Abilities in LLMs. arXiv (cs.AI), arXiv:2512.20845v2. 2026. https://arxiv.org/html/2512.20845v2
81. Multi-Agent Debate Strategies: Survey, Taxonomy, and Challenges. arXiv (cs.SE), 2607.26212v1. 2026. https://arxiv.org/html/2607.26212v1
82. CortexDebate: Debating Sparsely and Equally for Multi- .... Findings of the Association for Computational Linguistics: ACL 2025. 2025. https://aclanthology.org/2025.findings-acl.495.pdf
83. Adaptive heterogeneous multi-agent debate for enhanced educational and factual reasoning in large language models | Journal of King Saud University Computer and Information Sciences. Journal of King Saud University Computer and Information Sciences. n.d.. https://link.springer.com/article/10.1007/s44443-025-00353-3
84. L-MAD: A Systematic Evaluation of Multi-Agent Debate Structures in Legal Reasoning. arXiv (cs.AI), arXiv:2607.09099v1. 2026. https://arxiv.org/html/2607.09099v1
85. [2403.02691] InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents. ACL 2024 Findings (arXiv:2403.02691). 2024. https://arxiv.org/abs/2403.02691
86. AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents. NeurIPS 2024 (Advances in Neural Information Processing Systems 37), Datasets and Benchmarks Track. 2024. https://proceedings.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html
87. NetInjectBench: Benchmarking Indirect Prompt Injection in Tool-Using Large Language Model Agents for Network Operations. arXiv (2607.10490v1). 2026. https://arxiv.org/html/2607.10490v1
88. AgentSentry: Mitigating Indirect Prompt Injection in LLM Agents via Temporal Causal Diagnostics and Context Purification. arXiv (2602.22724v1, cs.CR). 2026. https://arxiv.org/html/2602.22724v1
89. AgentShield: Deception-based Compromise Detection for .... arXiv (2605.11026v1). 2026. https://arxiv.org/html/2605.11026v1
90. AI Agents That Matter. Transactions on Machine Learning Research (TMLR). 2024. https://www.semanticscholar.org/paper/AI-Agents-That-Matter-Kapoor-Stroebl/edae954314571eb2913209a7e9825cdc14fd4c58
91. Revisiting SWE-Bench: On the Importance of Data Quality for LLM-Based Code Models. 2025 IEEE/ACM 47th International Conference on Software Engineering: Companion Proceedings (ICSE-Companion), Ottawa. 2025. https://ieeexplore.ieee.org/document/11024333
92. SWE-Bench+: Enhanced LLM Coding Benchmark. AIware '26 (3rd ACM International Conference on AI-powered Software), Montreal (anonymous submission, OpenReview). 2026. https://openreview.net/pdf/f39d33e424d2af8ca2a6e1380c41eddfcaa49122.pdf
93. SWE-Bench+: Enhanced LLM Coding Benchmark | Proceedings of the 3rd ACM International Conference on AI-Powered Software. AIware '26: Proceedings of the 3rd ACM International Conference on AI-Powered Software. 2026. https://dl.acm.org/doi/10.1145/3805760.3814924
94. Automated Design of Agentic Systems. Semantic Scholar record (lists International Conference on Learning Representations; arXiv abs/2408.08435). 2024. https://www.semanticscholar.org/paper/Automated-Design-of-Agentic-Systems-Hu-Lu/c9537f656e7d9713fd4108ce7bf512290f48e562

## How this survey was produced

This survey was written by a research harness: it planned the outline, searched the web for scholarly sources, read 108 pages into typed notes, built the organising framework from those notes, wrote each section from its evidence, had a referee pass review the draft, and assembled the paper with 94 cited references. A person approved the outline before any source was read and the paper before it was published. Generated 2026-09-30T12:44:38+00:00.