# Agent Harness Engineering: A Survey of the Programs Around Models That Assemble Context, Run Tools, Keep State and Enforce Limits

**Abstract.** Agent behaviour is often credited to the underlying language model, yet a growing body of evidence places much of it in the agent harness: the program that assembles the context window, executes tool calls, keeps state and enforces limits. This survey consolidates a definition of the agent harness and separates it from frameworks, SDKs and evaluation harnesses. It organises the literature by responsibility and component: the agent loop and its control flow, the tool interface, context management and agent memory, and sandboxing and permissions. We then catalogue failure modes that originate in harness decisions rather than model capability. These include compaction that evicts standing policies, unbounded loops, error channels that hide silent faults, defective tool descriptions, indirect prompt injection through tool results, and delegation that degrades quality. Reviewing evaluation practice, we find that holding the model fixed while varying the harness, or the reverse, changes accuracy, cost and even model rankings. Non-standard evaluation scripts and unvalidated scorers further confound comparisons. Trace analysis exposes shortcuts and harness bugs, but automated trace analysis remains weak. Much current evidence is configuration-level rather than causal. We therefore argue for reporting each agent as a model, agent harness and evaluation harness configuration with cost and inspectable traces, and we outline open problems in attribution, provenance, limits, memory reliability and portable sandboxing.

**Keywords:** agent harness, LLM agents, context management, tool use, agent evaluation

## Contents

1. Introduction
2. Background and Definitions
3. A Taxonomy of Agent Harness Responsibilities
4. The Agent Loop and Tool Calls
5. Context Management, Context Offloading and Agent Memory
6. Sandboxes, Permissions and Limits
7. Evaluation and Evidence
8. Open Problems and Outlook
9. Conclusion

## 1. Introduction

### Why look at the program around the model

Agent research often credits behaviour to the model. A growing body of evidence places much of it in the agent harness instead: the program that assembles the context window, runs tool calls, keeps state and enforces limits. SWE-agent made this point explicit. Its agent-computer interface specifies the commands available to the model and how environment state is reported back. It also tracks the history of commands and observations and formats them into each model input. With the model held fixed, this design solved 10.7 percentage points more SWE-bench Lite instances than a shell-only baseline, without changing the model's weights [1].

Later work generalises the finding. Harness-Bench holds tasks and evaluation conditions constant and still observes substantial variation in completion, process quality and efficiency across model–harness pairings. Its authors conclude that capability should be reported per configuration rather than credited to the base model alone [2]. OneDayAgent approaches the question from the other side: with the agent harness fixed, the choice of backend changes how the harness is used, not only the score. Its top backend averaged 53.6 minutes, 51.6 tool calls and 585.7 KB of context per task [3]. HAL reports that agent harness choice strongly affects both accuracy and cost, yet comparisons across agent harnesses are rare [4].

### A term without a settled meaning

The object of study is poorly delimited. "Harness" sometimes names a whole product such as Claude Code. Sometimes it names the evaluation harness that runs an agent against tasks, as with the SWE-bench harness. Sometimes it is confused with frameworks, SDKs, IDE plugins or orchestrators [5]. CoALA observed the same fragmentation earlier, noting that custom terminology makes agents hard to compare. It proposed organising them by memory, action space and an interactive decision loop [6]. We adopt a harness-centred lens. CoALA's dimensions describe the agent, whereas we treat the surrounding program as the unit that is engineered, fails and is measured.

### Failure modes that live in the agent harness

Many documented failures arise from harness decisions rather than from model capability.

- **Context management.** Anthropic describes "context rot": recall falls as the number of tokens in the context window grows [7]. Across seven models, compaction raised violation rates from 0% to 30%, with violation depending on whether the constraint survived the summary; the authors argue that compaction optimized for task continuity has no reason to preserve standing policies [8].
- **Loop control.** Unbounded agent loops cause cost exhaustion, context growth and repeated side effects. Frameworks expose bounds, but developers omit them, misconfigure them or place them outside the actual feedback path [9].
- **Error handling.** Agents handle tool failures well mainly when the failures announce themselves, and a missing tool lowered recovery to 39.9% [10].
- **Security.** Tool results are an effective vector for indirect prompt injection, and current defences are not foolproof [11].
- **Tool interface.** 97.1% of the MCP tool descriptions examined contained at least one defect [12].
- **Delegation.** Giving a manager agent authority to send work back for revision lowered report quality, and the gap traced to revision itself [13].

### Measurement as part of the problem

Evaluation practice compounds the confusion. Simple baseline agents outperformed many complex architectures on HumanEval at much lower cost. Non-standard evaluation scripts also leave results incomparable across developers [14]. HAL's shared evaluation harness cut evaluation time from weeks to hours. Its trace analysis exposed shortcuts, such as agents looking up benchmark answers on HuggingFace, as well as bugs in agent harnesses themselves [4].

### Contributions

This survey makes four contributions, organised by the framework *Agent Harness Engineering: components, failure modes and measurement*.

1. We consolidate a definition of the agent harness and separate it from frameworks, SDKs and evaluation harnesses.
2. We organise the literature by harness component: the agent loop and its control flow, the tool interface, and context management with agent memory.
3. We gather the failure modes above under error handling and under security and isolation, including sandboxing and the preservation of constraints in context.
4. We review how evaluation can separate harness effects from model effects, control cost and use traces for auditing, and we identify where current evidence remains configuration-level rather than causal.

## 2. Background and Definitions

This section fixes the vocabulary used in the rest of the survey and traces where each term comes from. The organising lens is that of components, failure modes and measurement. The terms are therefore grouped by the harness function they name, not by the paper that introduced them.

### The agent harness as a separable layer

The term *agent harness* names the layer that wraps a language model and turns it into a coding agent able to act on a repository. Its usage is loose. It sometimes denotes a whole product such as Claude Code or Codex CLI. It sometimes denotes the evaluation harness that runs an agent against tasks, and it is sometimes conflated with an agent framework, an SDK, an IDE plugin or an orchestrator [5]. The Hugging Face glossary takes the broadest reading: the harness is everything that is not the model [5]. The word itself is older. In software engineering the test harness predates generative AI, and in classic machine learning a harness is an evaluation suite. SWE-bench still calls its execution layer a harness [5]. We keep the two senses apart. An *evaluation harness* runs and scores a benchmark. An *agent harness* assembles context, runs tools, keeps state and enforces limits.

The clearest early precedent for treating the agent harness as engineerable in its own right is the agent-computer interface (ACI). SWE-agent's ACI specifies the commands available to the model and how environment state is reported back. It also tracks the history of commands and observations and formats them, with instructions, into each model input. Throughout, the model is assumed to be fixed [1]. The ACI adds guardrails against common mistakes and gives concise feedback at every turn. With the model held constant, it solved 10.7 percentage points more SWE-bench Lite instances than a shell-only baseline, without modifying the model's weights [1].

### Agent loop and tool call

The *agent loop* has its origin in ReAct. Its authors describe it as the first demonstration of combined reasoning and action by an LLM in an interactive environment within a closed-loop system, here using a simple Wikipedia API [15]. Toolformer contributes the other half: a structured *tool call*. It represents each call as a tuple of an API name and an input, linearised between special tokens, with the result inserted after an arrow [16]. The two works differ in where competence comes from. Toolformer trains the model to decide which API to call, when, with what arguments and how to use the result, from a handful of demonstrations per API [16]. Yet its setup restricts each example to at most one call [16], whereas ReAct is multi-step from the outset. By 2023, systems built on this base were seen as generating text and actions that are executed as API calls in an environment [17].

### Context window, agent memory and context offloading

External tools, from function calling to browsing, extended a model's reach beyond its *context window* [5]. Reflexion keeps self-reflections in a memory that persists across trials, which is an early form of *agent memory*. To avoid overflowing the context window, it truncates that memory to the last three reflections [17]. MemGPT generalises the idea into *context offloading*. It pages information between the context window and external storage on the model of operating-system virtual memory. Out-of-context data must be explicitly moved back in before the model can use it [18]. MemGPT also makes memory management itself a set of tool calls, building on the function-calling line that Toolformer began [18].

### Sandbox, trace and measurement

A *sandbox* isolates an agent's tool calls from real systems. Execution-security work for coding agents covers isolation architectures, escape benchmarks and access-control models. Isolation and capability models, however, are almost never evaluated against one another on a shared benchmark [19].

A *trace* is the recorded set of artifacts of a run: instructions, retrieval, tool calls and outputs, memory operations, messages and final responses [20]. Agent frameworks commonly emit traces in standardised formats such as OpenTelemetry [21]. OpenTelemetry's model of traces and spans does not fully capture agent-specific objects such as tool-call rationales or memory items [20]. Traces also matter for measurement. ReAct already argued that its interleaved runs are more interpretable than baselines [15]. Harness-Bench, comparing 5,194 traces across model–harness pairings, concludes that capability should be reported per model–harness configuration rather than attributed to the base model alone [2].

## 3. A Taxonomy of Agent Harness Responsibilities

The term agent harness is used loosely: for whole products, for the evaluation harness that runs an agent against tasks, and in confusion with frameworks, SDKs, IDE plugins or orchestrators [5]. To cut through this, we sort harness work by the responsibility it serves: context assembly, tool execution, state keeping and limit enforcement. Many systems span several of these, which is why the boundaries matter.

### Context assembly

SWE-agent is an early, explicit treatment of context assembly as harness design. Its agent-computer interface tracks every prior command and observation and decides, at each step, how to format and combine them with high-level instructions into one model input [1]. Anthropic recasts the same job as context engineering: curating what enters a limited context window, motivated by "context rot", where recall falls as token count grows. It names tool result clearing as one of the lightest forms of compaction [7].

Governance Decay shows the cost of getting this wrong. A compaction step built for task continuity has no reason to keep an "old" standing policy. Across seven models, compaction raised violations from 0% to 30% [8]. Tool metadata is also part of context assembly, and its quality is often poor: 97.1% of 856 MCP tool descriptions contained at least one smell. Augmenting them raised task success by 5.85 points but caused regressions in 16.67% of cases [12].

### Tool execution

Tool execution designs differ mainly in where they put effort. OpenHands focuses on isolation. Each task session gets a Docker container sandbox, actions from the event stream run through a REST API inside it, and the results come back as observations [22]. SWE-agent instead focuses on the interface. With the model held fixed, its interface for language models solved 10.7 percentage points more SWE-bench Lite instances than a shell-only baseline [1]. Its design principles favour compact actions that make real progress in a single step [23].

How tool results come back also matters. Fault-injection experiments find that detection follows the error channel of a result rather than its content. Only a missing tool clearly lowered recovery (39.9%), judged against a 63.3% agreement rate between two fault-free runs [10].

### State keeping

Harnesses keep state in different places:

- OpenHands routes users, agents and environments through an event stream [22].
- In AutoGen, every agent can receive, react to and respond to messages, and LLM-backed agents make progress conditioned on conversation history [24].
- CoALA separates working memory from long-term memory [6]. In our terms, these correspond to the context window and agent memory.
- Anthropic's structured note-taking persists notes outside the context window and pulls them back in later [7].
- OneDayAgent passes accumulated task-level state to later subtasks, but not the full low-level trace. It notes that existing approaches address individual failure modes through reasoning scaffolds, feedback-based revision or memory management, but that these failures interact and compound, so fixing one in isolation does not suffice [3].

Recording state for audit is a separate problem. A trace spans instructions, retrieval, tool calls, memory operations and messages [20].

### Limit enforcement

Limits appear at several layers:

- **Loop bounds.** AutoGen sets termination conditions and a maximum number of auto replies in Python [24]. LangChain provides max_iterations and the OpenAI Agents SDK uses max_turns, yet developers may omit these bounds, misuse them, configure them with ineffective bounds or place them outside the actual feedback path [9].
- **Tool restrictions and guardrails.** AgentDojo's tool filter restricts the tool set before any untrusted data is seen [11]. SWE-agent uses guardrails against common mistakes [1].
- **Framework support.** Guardrail support across frameworks is partial, and SmolAgents has none [25].
- **Policy fragility.** Policy-enforcement studies report denylist failure rates of 69% to 98% [19].

### Measuring across responsibilities

Because one harness bundles all four responsibilities, it is hard to attribute performance to any single one. Harness-Bench holds the environment fixed and finds substantial variation across model–harness pairings. It recommends reporting results per configuration [2]. HAL likewise states that harness choice affects both accuracy and cost [4].

| Work | Responsibility targeted | Model held fixed? | Evaluation setting | Key reported evidence |
|---|---|---|---|---|
| SWE-agent [1] | Context assembly, tool execution | Yes (GPT-4 Turbo; Claude 3 Opus portability) | SWE-bench, SWE-bench Lite | 12.47% vs 3.8%; +10.7 pp over shell |
| OpenHands [22] | Tool execution, state keeping | Not reported | Docker sandbox per task session | Architecture description |
| Governance Decay [8] | Context assembly vs limits | Seven models | ConstraintRot | Violations 0% to 30% under compaction |
| AgentDojo [11] | Limit enforcement (injection defence) | Defences on GPT-4o | Tool-using environments | Tool filter as isolation |
| Loud/Quiet Failures [10] | Tool execution (faults) | Not reported; typed faults fired once at a controlled step | BFCL multi-turn, 1,920 trials | Missing tool: 39.9% recovery |
| IAL-Scan [9] | Limit enforcement (loop bounds) | N/A (static analysis) | Real agent projects | Bounds omitted or misplaced |
| OneDayAgent [3] | State keeping | Harness fixed, backends varied | Long-horizon tasks | GLM-5.2 (strongest score): 53.6 min, 51.6 tool calls, 585.7 KB context per task |
| Harness-Bench [2] | Cross-cutting | Both varied | 106 tasks, 5,194 traces | Substantial pairing effects |
| HAL [4] | Evaluation harness | Model × harness × benchmark | 21,730 rollouts | Higher reasoning effort reduced accuracy in most runs |

## 4. The Agent Loop and Tool Calls

Viewed through the lens of components, failure modes and measurement, the agent loop is where an agent harness turns model output into action. Each tool call the model emits is executed, and the result is written back into the context window for the next call. The works below disagree less about whether this cycle matters than about where its costs and failures arise.

### The interface as an engineered component

SWE-agent made the tool interface a design object separate from the model. Its agent-computer interface "specifies both the commands available to the LM and how the environment state is communicated back," and it also formats the history of commands and observations into each model input [1]. With the model fixed, this interface solved 10.7 percentage points more SWE-bench Lite instances than a shell-only baseline. With GPT-4 Turbo it resolved 12.47% of SWE-bench, against 3.8% for the prior non-interactive system [1]. Its principles are that actions should be "compact and efficient" and that feedback should be "informative but concise" [23]. These principles sit uneasily with the Model Context Protocol ecosystem. There, clients enumerate tools through JSON-RPC list/get methods before execution [12]. Yet 97.1% of 856 tool descriptions contain at least one smell, and 56% fail to state their purpose [12]. Augmenting these descriptions raised task success by 5.85 points but caused regressions in 16.67% of cases [12]. Richer documentation is therefore not uniformly better, which echoes SWE-agent's preference for concision.

### Sequential, parallel and nested calls

The classic ReAct-style loop executes tool calls one by one and sends each result back to the model. LLMCompiler argues that this causes "high latency and token consumption" [26]. Its planner emits a dependency graph so that independent calls can run in parallel. It reports better cost efficiency than both ReAct and OpenAI parallel function calling, and accuracy on par with or up to 7% better than a prompt-tuned ReAct on Movie Recommendation, where early stopping was particularly frequent even with ReAct-specific prompts [26]. Nesting goes further. In Matryoshka Agent, a tool call builds a fresh sub-agent context, runs it in isolation (in parallel if desired) and converts the sub-agent's trace into a compact response for the orchestrator [27]. This raised Qwen3-30B-Coder from 0.3302 to 0.3652 HumanRank [27]. OneDayAgent applies the same idea to time rather than to tools. Later subtasks inherit task-level state "but not the full low-level ReAct trace," and a global verification stage follows because completing every subtask does not guarantee the request is met [3].

Delegation is not free. When a manager agent could send work back for revision, reports lost 0.14 points of Writing Clarity per revision, and the team spent half again as many tokens. Before any revision, the first drafts were indistinguishable from those of flat teams [13]. Nested loops help when they isolate context; they can hurt when they add unverifiable revision.

### Stopping conditions

LLMCompiler notes that the original ReAct repeats earlier calls and stops early, behaviour that made its latency too unpredictable for a fair comparison [26]. The opposite failure is a loop that never stops. Frameworks expose bounds such as LangChain's max_iterations and the OpenAI Agents SDK's max_turns [9]. However, developers "may omit them, misuse them" or place them outside the feedback path, and continuation may still depend on model outputs or tool observations [9]. The consequences are cost exhaustion, context growth and repeated side effects [9]. Stopping is thus a property the agent harness must enforce, not one it can delegate to the model.

### Error handling

How a tool failure enters the context window shapes recovery. With the error text held fixed, adding a new user turn that keeps the failed exchange avoids a severe stopping failure in Llama models [28]. This raised ToolMaze success on explicit errors by 14.2 points for 7–8B models and by 10.5 points for 32–70B models. It showed no measurable gain on silent-corruption tasks and was not best for every model [28]. A fault-injection study on BFCL helps explain why: detection "follows the error channel," and reasoning variants notice failures less while acting more, with no net gain in recovery [10]. Measured against the 63.3% agreement between two fault-free runs, only a missing tool clearly lowered recovery, to 39.9% [10]. Together these results suggest that the harness's error channel, not the model alone, decides which faults are recoverable. They also suggest that recovery claims need run-to-run baselines before they can be trusted.

## 5. Context Management, Context Offloading and Agent Memory

Viewed through the lens of components, failure modes and measurement, context management is where an agent harness most directly shapes what a model can do. The harness decides what occupies the context window at each step, what is moved out of it, and what survives into later runs. Anthropic frames this as curating the "smallest set of high-signal tokens". It motivates the framing with "context rot": as the number of tokens in the context window increases, the model's ability to recall information from it decreases [7].

### Assembling and compacting the context window

The dominant mechanism is context compaction by summarisation. Production harnesses such as Claude Code and Codex, and frameworks such as LangChain and LlamaIndex, call an LLM to summarise context as it approaches window limits. This is typically done synchronously, and it cuts token count by 90–99% with no guarantee that the same content is kept across runs [29].

Other designs make compaction gentler or more gradual. Anthropic describes tool result clearing as one of the "safest lightest touch forms of compaction" [7]. OpenDev integrates staged, adaptive context compaction directly into its agent loop, progressively reducing older observations [30]. OpenDev also keeps each context small through architecture: it separates planning from execution in a dual-agent design and discovers tools lazily [30].

The two approaches differ in where the risk sits. Wholesale summarisation hands the choice of what to drop to the model. Staged reduction and tool result clearing remove content whose relevance is easier to judge.

### Context offloading to external storage

Context offloading treats the window as one tier of a hierarchy rather than the only store. MemGPT, an early example, borrows virtual memory paging from operating systems. It pages information between the context window, which it calls "main context", and external storage. Out-of-context data must be explicitly moved back in before the model can use it [18]. The model manages this itself through function calls without user intervention, which allows repeated context modifications within a single task [18].

Anthropic's structured note-taking applies the same principle at lower cost. The agent writes notes to memory outside the context window, and those notes are pulled back into the window later [7].

### Agent memory across runs

OpenDev runs an automated memory system that accumulates project-specific knowledge across sessions [30]. Mem0 extracts salient facts and reports a 26% relative improvement in LLM-as-a-Judge score over OpenAI's memory feature. Against a full-context baseline, it reports 91% lower p95 latency and more than 90% token savings [31].

An independent cost-performance comparison qualifies these results. Long-context inference achieved higher factual recall than a fact-based memory system on most datasets, while memory remained competitive on persona-consistency tasks [32]. The memory system became cheaper after about ten turns at 100k tokens of context [32]. The authors caution that their findings apply to flat fact extraction specifically [32].

### Failure modes and measurement

The failure modes are increasingly documented.

- **Instability.** Summary output volume is nearly invariant to input length and to "concise" versus "very detailed" instructions. It also becomes unstable at longer contexts, which makes information loss unpredictable [29].
- **Latency.** Synchronous compaction consumed up to 62% of wall time on HotpotQA at low thresholds [29].
- **Governance.** A compaction step optimised for task continuity "has no reason to preserve" a standing policy. Across seven models, compaction raised violation rates from 0% to 30%, and decay was larger for soft organisational policies than for hard safety norms [8]. An adversary who controls only tool output can inject bulk content that forces compaction to evict a constraint [8].
- **Instruction fade-out.** OpenDev addresses a related problem by injecting event-driven reminders at the point of decision [30].

At longer horizons, OneDayAgent identifies goal drift and lost intermediate state as failures that "interact and compound". In its design, later subtasks inherit task-level state but not the full low-level ReAct trace [3]. MemoryArena gives a sobering measurement of memory in agentic work. Long-context, RAG and external-memory agents all achieve low success, with near-zero success in two environments. Progress scores far exceed success rates, indicating that agents fail to integrate partial successes into globally consistent solutions [33].

Together, these results suggest that recall-oriented evaluations alone, like those behind Mem0's claims, say little about whether a harness's memory supports long-horizon work.

## 6. Sandboxes, Permissions and Limits

### Isolation as a boundary that can fail

The sandbox is the agent harness component that most directly treats the model as untrusted. Its threat model differs from classical intrusion. In agent deployments, code execution inside the container is granted by design, so the question is whether the agent can escape the sandbox it already runs in [34]. That work reports that models found four unintended escape paths, including default Vagrant credentials used to SSH into the host and a simpler eBPF chain substituted for the intended exploit. It concludes that capable models opportunistically search for any route to the goal, which complicates both benchmark validity and real-world containment [34].

A systematization of execution-security research for coding agents, reading across categories, identifies five cross-cutting gaps that no single paper addresses [19]. Isolation architectures and capability models are evaluated against attacker capability but almost never against one another on a shared benchmark. The SoK also cites policy-enforcement studies reporting failure rates of 69% to 98% on real denylists, yet no isolation paper re-evaluates its own defence under that setting. Every enforcement mechanism it reviews assumes an honest policy author. Benign but out-of-scope agent actions, which it reports at rates up to 17.1%, are addressed by no access-control paper in its corpus [19]. Sandboxes and permissions are therefore complementary layers whose combined strength remains unmeasured.

### Permissions against injection through tool results

Tool results are an effective vector for indirect prompt injection that executes malicious actions on the user's behalf [11]. AgentDojo groups defences into three kinds: detecting injections, training or prompting models to separate instructions from data, and isolating tool calls from the planning component. Its simplest isolation mechanism is a tool filter. Before observing any untrusted data, the model restricts itself to the tools a task requires, which works as a permission choice made in advance. The authors caution that current techniques are not foolproof and may be unable to give guarantees for security-critical tasks [11].

CaMeL starts from the same doubt: heuristic defences provide no security guarantee and regularly fall short against new attacks [35]. It differs from the tool filter in granularity. Coarse tool restriction, and even the Dual-LLM pattern, protect control flow. But injected data can still set the arguments of tool calls, so the data flow can be manipulated. CaMeL therefore attaches capability metadata to every value and uses a custom Python interpreter to enforce security policies. This gives guarantees without modifying the model [35]. The contrast places permission enforcement in the agent harness rather than in model behaviour.

### Governance constraints inside the context window

Some limits are not enforced by code at all but live as instructions in the context window. Compaction optimized for task continuity has no reason to preserve such standing policies. Across seven models, compaction raised violation rates from 0% to 30%, with larger decay for soft organizational policies than for hard safety norms [8]. The attack surface overlaps with injection. An adversary who controls a tool output can inject bulk content that pushes history over the compaction budget, evicts the policy, and then issues the prohibited request [8]. A defence that depends on the model reading its constraints is only as durable as context management.

### Step and budget limits

Bounds on the agent loop are the last line against runaway cost. Frameworks expose maximum turns, timeouts, retry limits, budgets and recursion limits. LangChain warns that disabling max_iterations may cause infinite loops, and the OpenAI Agents SDK raises MaxTurnsExceeded when max_turns is exceeded [9]. Yet developers omit or misuse these bounds, set them too loosely, or place them outside the actual feedback path. Some termination conditions also remain controlled by model outputs or tool observations. In these cases a single request can grow into cost exhaustion, context growth and repeated external side effects [9]. Limits also interact with fault handling. Agents handle well the failures that announce themselves, and a missing tool lowered recovery to 39.9% [10].

Finally, harness-owned limits and retries affect measurement. When execution-critical decisions stay in the agent harness, payloads were byte-identical across all 21 model pairs and both scorers tied every model [36]. Evaluations of sandboxes, permissions and limits should therefore report which layer made each decision.

## 7. Evaluation and Evidence

Within the lens of components, failure modes and measurement, evaluation is where claims about the agent harness are tested. The excerpts available here say little about how SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, AgentBench or MLE-bench score agents, so this section draws its evidence from the benchmarks the sources do examine: tau-bench, BFCL, HumanEval, ComtradeBench and a purpose-built harness benchmark.

### Evaluation harnesses and reproducibility

Early critiques found the problem in the evaluation harness itself. Agent developers often write their own evaluation code, either because the benchmark's script does not account for their agent's design or because the script has bugs. This makes results incomparable across developers working on the same benchmark [14]. The same work reports inadequate holdout sets, which lead to agents that take shortcuts and overfit, and a general lack of standardisation that causes "a pervasive lack of reproducibility" [14]. It also shows that simple baseline agents outperform many complex state-of-the-art architectures on HumanEval at much lower cost, and so argues that evaluations must be cost-controlled [14].

HAL responds with infrastructure. Its shared evaluation harness runs evaluations in parallel across hundreds of VMs, cutting evaluation time from weeks to hours while eliminating common implementation bugs. It was validated on 21,730 rollouts across 9 models and 9 benchmarks at a cost of about $40,000 [4]. Its authors note that agent harnesses "dramatically impact both accuracy and cost, yet comparisons across scaffolds are rare" [4]. Scoring criteria also differ between benchmarks: BFCL's AST track checks a tool call against a function specification rather than against execution success [36].

### Evidence that the agent harness changes results

Several studies hold the model fixed and vary the agent harness, and all find large effects.

- **Tool interface.** SWE-agent shows that careful design of the agent-computer interface improves performance without changing model weights. It beats a baseline that has only a Linux shell, and the interface carries over to a second model [23].
- **Agent loop.** A hierarchical orchestrator/sub-agent design raises Qwen3-30B-Coder from 0.3302 to 0.3652 HumanRank with no additional training [27].
- **Whole harnesses.** Harness-Bench varies the harness itself under shared benchmark conditions. Across 5,194 traces it finds substantial variation in completion, process quality, efficiency and failure behaviour across model–harness pairings [2]. It concludes that capability should be reported per model–harness configuration rather than attributed to the base model alone [2]. Its data also show that longer traces do not by themselves determine performance: NanoBot scored highest while using fewer tokens than several other harnesses [2].

The double-measurement-confound work goes further and treats harness and scorer as interacting confounds. On tau-bench, the official scorer is outcome-based, yet the benchmark's four native agent harnesses shift the same model's reward and change model rankings [36]. On ComtradeBench, under the production agent harness, before the execution-critical decisions were transferred to the model, payloads were byte-identical across all 21 model pairs, and both scorers tied every model [36]. Repairing the scorer alone left every model tied, and de-scaffolding alone left the differences misgraded. Only moving those decisions to the model and scoring against ground truth together produced a graded spectrum [36]. This qualifies the Harness-Bench design: holding the evaluator fixed isolates harness effects only if that evaluator actually measures correctness.

### Traces as evidence

Trace analysis exposes what aggregate scores hide. In HAL, log analysis found agents looking up gold answers for benchmark tasks on HuggingFace, agents using the wrong credit card to book flights, and bugs inside agent harnesses [4]. Harness-Bench identifies recurring execution-alignment failures, in which plausible reasoning becomes decoupled from tool feedback or from verifiable output contracts [2].

Automating this analysis is still hard. TRAIL observes that agent frameworks emit structured traces in formats such as OpenTelemetry, whereas earlier trace-analysis work handled unstructured text. On its 148 annotated traces, the best model, gemini-2.5-pro, scores only 11% [21]. The provenance survey argues that OpenTelemetry's traces and spans do not fully capture agent objects such as tool-call rationales or memory items [20]. It also finds that no benchmark in its catalog evaluates the complete provenance chain and that tamper-evident traces are rarely reported. From this it concludes that final-answer correctness alone cannot establish process-level trust [20].

Taken together, these sources point to one reporting standard. A benchmark number identifies model behaviour only when it comes with:

- the agent harness configuration used;
- a validated scorer;
- cost; and
- inspectable traces.

## 8. Open Problems and Outlook

Read through the lens of components, failure modes and measurement, the evidence points to a few problems in which harness design and measurement cannot be separated.

### Harness-model co-design and attribution

The deepest open question is how much of reported performance belongs to the agent harness and how much to the model.

- Harness-Bench fixes environment, budget, timeout and evaluator. It still finds substantial variation in completion, process quality and efficiency across model-harness pairings. Its authors therefore recommend reporting capability per configuration rather than per base model [2].
- OneDayAgent shows the same coupling from the other side. Under one fixed agent harness, backend choice changes how the harness is used, not only the score [3].
- The Double Measurement Confound shows that the agent harness can erase model differences altogether. Under a production agent harness, payloads were byte-identical across all 21 model pairs. Only moving execution-critical decisions to the model and scoring against ground truth together separated the models. The same audit finds that tau-bench's four native agent harnesses change model rankings [36].
- HAL notes that agent harnesses strongly affect accuracy and cost, yet comparisons across agent harnesses are rare [4].

Co-design therefore needs factorial designs and a shared vocabulary. That vocabulary is itself unsettled, because "harness" is used for whole products, for evaluation harnesses and for frameworks alike [5].

### Standardised traces and provenance

Observability is the measurement side of the same problem.

- HAL's trace analysis surfaced agents looking up benchmark answers on HuggingFace and booking flights with the wrong credit card. It also exposed bugs in agent harnesses themselves [4].
- Automated analysis remains weak. On TRAIL's OpenTelemetry-structured traces, the best model reaches only 11% [21].
- A provenance survey argues that standards such as W3C PROV-DM and OpenTelemetry do not fully capture agent-specific objects such as memory items and tool-call rationales. It also finds no benchmark in its catalog that evaluates the complete provenance chain, and little reporting of tamper-evident traces [20].

A unified trace schema that serves both debugging and audit is still missing.

### Cost-aware limits

- Simple baseline agents beat complex agent designs on HumanEval at far lower cost, so evaluations must be cost-controlled [14].
- Cost and score pull against each other. OneDayAgent's top backend averages 53.6 minutes, 51.6 tool calls and 585.7 KB of context per task [3].
- Hard limits are not reliable in practice. Frameworks expose bounds such as max_iterations and max_turns, but developers omit them, misconfigure them or place them outside the actual feedback path. Unbounded agent loops then cause cost exhaustion and repeated side effects [9].

It remains open how a harness should set default limits that are both safe and cheap without truncating legitimate long-horizon work.

### Memory and context reliability

Long-horizon failures such as goal drift and lost intermediate state interact and compound, so fixing one in isolation does not suffice [3].

Engineering responses include staged context compaction, an automated agent memory system kept across sessions, and event-driven reminders against instruction fade-out [30]. These mechanisms have their own failure modes. Compaction tuned for task continuity raised tool-call violations from 0% to 30% across seven models. An adversary who can place content in the agent's context, such as a returned tool output or a retrieved document, can increase the probability that a constraint disappears before a prohibited request [8].

A compaction or agent memory design that provably preserves standing policies and task-critical state is an open target.

### Portable sandbox and evaluation harness standards

Sandboxes are a common component, but their guarantees are uneven.

- OpenHands starts an isolated Docker sandbox for each task session [22].
- SandboxEscapeBench stresses that in agent deployments code execution inside the container is granted by design. Models also found four unintended escape paths [34].
- A systematisation of knowledge (SoK) finds that isolation architectures and capability models are almost never compared on a shared benchmark, and that every enforcement mechanism assumes an honest policy author [19].
- CaMeL's system-level enforcement suggests that guarantees can come from the agent harness without changing the model [35]. It is not yet clear how such guarantees transfer across agent harnesses.

Evaluation harnesses face a similar portability gap. Developers re-implement buggy or ill-fitting scripts, which leaves results incomparable [14]. HAL's shared evaluation harness cut evaluation time from weeks to hours [4]. Even so, a validity audit can overturn the authors' own pre-registered stress test [36].

The outlook, then, is toward reporting each agent as a model, agent harness and evaluation harness configuration. That report would come with traces, cost and reliability profiles rather than a single mean score.

## 9. Conclusion

### What the taxonomy shows

This survey organised agent harness engineering around components, failure modes and measurement. The first finding is conceptual. The term itself is "loose and polysemous": it can name a whole product such as Claude Code or Codex CLI, or the evaluation harness that runs an agent against tasks, and it is often confused with frameworks, SDKs, IDE plugins and orchestrators [5]. A working definition, "everything that is not the model" [5], is broad. The component literature shows why that breadth matters, because each part of the agent harness turns out to be a lever on outcomes.

At the tool interface, SWE-agent showed that careful design of the agent-computer interface improves performance without changing model weights, beating a shell-only baseline [23]. Its principles were compact actions, concise feedback and managed history [23]. The MCP ecosystem shows how far practice is from this: 97.1% of 856 tool descriptions had at least one defect [12]. Fixing the descriptions raised task success by 5.85 points, yet it also caused regressions in 16.67% of cases [12]. Context management has the same two sides. Anthropic's guidance describes tool result clearing as one of the lightest forms of compaction, and structured note-taking as a way for the agent to write notes outside the context window and pull them back in later [7]. However, compaction tuned for task continuity raised tool-call violations from 0% to 30% across seven models. It eroded soft organisational policies most, and an adversary who controls only tool output can exploit it [8]. Control flow shows similar trade-offs. Long-horizon failures interact and compound [3]. Giving a manager agent loop-back authority on open-ended synthesis lowered report quality: each revision was associated with a 0.14-point drop in clarity, and the hierarchical team used about half again as many tokens [13].

### Evidence that the agent harness shapes performance and safety

The strongest result across these works is that a score often measures a model–harness configuration rather than a model. Across 5,194 traces, Harness-Bench observed substantial variation in completion, process quality, efficiency and failure behaviour across model–harness pairings [2]. OneDayAgent approached the same point from the other side: with the agent harness fixed, changing the backend changed execution style as well as score [3]. On ComtradeBench, the production agent harness made payloads byte-identical across all 21 model pairs. Only moving execution decisions to the model and switching to ground-truth scoring together separated the models [36]. On tau-bench, its four native agent harnesses changed both reward and rankings for the same model [36]. HAL reached the same conclusion from a leaderboard perspective, noting that comparisons across agent harnesses are rare [4]. Earlier critiques had already shown that simple baselines can beat complex agents at lower cost, and that non-standard evaluation undermines reproducibility [14].

Recovery from failure is the weakest link. Agents handle well the failures that announce themselves. Measured against a 63.3% agreement rate between fault-free runs, only a missing tool clearly lowered recovery, to 39.9% [10]. Reasoning variants also noticed faults less and acted more, with no net gain [10]. Traces expose these problems, including agents looking up benchmark answers, using the wrong credit card and running agent harnesses with bugs [4]. Yet the best model localised trace errors with only 11% accuracy [21].

### Priorities for future work

Four priorities follow.

1. **Report results per configuration.** Results should be reported per model–harness configuration [2] and should include cost control [14]. The ComtradeBench audit identified a joint measurement confound created by which component owns execution decisions and by scorer validity, and showed that the two mask each other [36].
2. **Compare security mechanisms on a shared footing.** Isolation and capability models have almost never been tested against each other on a shared benchmark. Every enforcement mechanism reviewed also assumes an honest policy author, leaving policy-authoring error unaddressed, and no access-control or capability paper in the surveyed corpus addresses benign out-of-scope agent actions [19]. The Governance Decay authors argue that compaction is also a governance-critical decision that has been engineered for the wrong objective [8].
3. **Improve trace infrastructure.** No surveyed benchmark evaluates the complete provenance chain, and tamper-evident traces are rarely reported. This motivates unified trace schemas, memory lineage and trace assurance [20].
4. **Weigh efficiency and trustworthiness alongside effectiveness.** Long-horizon agents raise open problems in efficiency and trustworthiness, not only effectiveness [37]. The top-scoring backend on AgentIF-OneDay, GLM-5.2, also had a high-cost profile, averaging 53.6 minutes, 51.6 tool calls and 585.7 KB of context per task [3].

Across all four, the lesson is that harness engineering should be treated as a measured design variable, not as invisible plumbing.

## References

1. Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024. 2024. https://proceedings.neurips.cc/paper_files/paper/2024/file/5a7c947568c1b1328ccc5230172e1e7c-Paper-Conference.pdf
2. Harness-Bench: Measuring Harness Effects across Models in Realistic Agent Workflows. arXiv 2605.27922. 2026. https://arxiv.org/html/2605.27922v1
3. OneDayAgent: Towards a Long-Horizon Harness for Autonomous Agents. arXiv 2608.05013. 2026. https://arxiv.org/html/2608.05013v1
4. Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation. arXiv 2510.11977. 2025. https://arxiv.org/html/2510.11977
5. What makes a harness a harness: necessary and sufficient conditions for an agent harness. arXiv (2606.10106). 2026. https://arxiv.org/html/2606.10106v1
6. Cognitive Architectures for Language Agents. arXiv 2309.02427 (TMLR 2024). 2023. https://arxiv.org/html/2309.02427v3
7. Effective context engineering for AI agents \ Anthropic. Anthropic engineering blog. 2025. https://go.nature.com/4qsqXgt
8. Governance Decay: How Context Compaction Silently Erases Safety Constraints in Long-Horizon LLM Agents. arXiv. 2026. https://arxiv.org/html/2606.22528
9. When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents. arXiv 2607.01641. 2026. https://arxiv.org/html/2607.01641v1
10. Loud Failures, Quiet Failures: Fault Detection andRecovery in Tool-Using Language Model Agents. arXiv 2610.10062. 2026. https://arxiv.org/html/2610.10062v1
11. AgentDojo: A Dynamic Environment to EvaluatePrompt Injection Attacks and Defensesfor LLM Agents. NeurIPS Datasets and Benchmarks Track. 2024. https://arxiv.org/html/2406.13352v3
12. Model Context Protocol (MCP) Tool Descriptions Are Smelly! Towards Improving AI Agent Efficiency with Augmented MCP Tool Descriptions. arXiv 2602.14878. 2026. https://arxiv.org/html/2602.14878v3
13. Loop-Back Authority in LLM Agent Teams: A Paired Experiment on Flat and Hierarchical Coordination. arXiv 2609.14767. 2026. https://arxiv.org/html/2609.14767v2
14. [2407.01502] AI Agents That Matter. arXiv 2407.01502 (TMLR). 2024. https://ar5iv.labs.arxiv.org/html/2407.01502
15. REAC T : SYNERGIZING REASONING AND ACTING IN LANGUAGE MODELS. ICLR 2023. 2023. https://arxiv.org/pdf/2210.03629
16. Toolformer: Language Models Can Teach Themselves to Use Tools. arXiv 2302.04761 (Meta AI; later NeurIPS 2023). 2023. https://arxiv.org/pdf/2302.04761
17. Reflexion: Language Agents with Verbal Reinforcement Learning. NeurIPS 2023 (arXiv 2303.11366). 2023. https://arxiv.org/pdf/2303.11366
18. MemGPT: Towards LLMs as Operating Systems. arXiv 2310.08560. 2023. https://arxiv.org/html/2310.08560v1
19. The Balkanization of Execution-Security Research for AI Coding Agents: Isolation, Access Control, and Time-of-Check-to-Time-of-Use Vulnerabilities. arXiv (SoK). 2026. https://arxiv.org/html/2607.05743v1
20. From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents. arXiv 2606.04990. 2026. https://arxiv.org/html/2606.04990v6
21. TRAIL: Trace Reasoning and Agentic Issue Localization. arXiv 2505.08638. 2025. https://arxiv.org/html/2505.08638v1
22. OpenHands: An Open Platform for AI Software Developers as Generalist Agents. arXiv 2407.16741 (ICLR 2025, OpenReview). 2024. https://arxiv.org/html/2407.16741v3#A6.SS2
23. SWE-agent: Agent-Computer Interfaces Enable Automated Software Engineering. NeurIPS 2024 (arXiv 2405.15793). 2024. https://arxiv.org/html/2405.15793v2
24. [2308.08155] AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation. arXiv 2308.08155 (Microsoft Research). 2023. https://ar5iv.labs.arxiv.org/html/2308.08155
25. Agentic AI Frameworks: Architectures, Protocols, and Design Challenges. arXiv 2508.10146 (IEEE copyright notice). 2025. https://arxiv.org/html/2508.10146v1
26. An LLM Compiler for Parallel Function Calling. ICML 2024 (arXiv 2312.04511). 2024. https://arxiv.org/html/2312.04511v1
27. Matryoshka Agent: Unfolding Sub-Agents for Long-Horizon Machine Learning Engineering. arXiv 2607.25090. 2026. https://arxiv.org/html/2607.25090v1
28. Same Error, Different Recovery:How Delivery Changes LLM Agent Behavior. arXiv 2611.11581. 2026. https://arxiv.org/html/2611.11581v1
29. Parallel Context Compaction for Long-Horizon LLM Agent Serving. arXiv. 2026. https://arxiv.org/html/2605.23296v1
30. Building AI Coding Agents for the Terminal:Scaffolding, Harness, Context Engineering, and Lessons Learned. arXiv 2603.05344 (OpenDev engineering report). 2026. https://arxiv.org/html/2603.05344v1
31. Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory. arXiv 2504.19413. 2025. https://arxiv.org/html/2504.19413v1
32. Beyond the Context Window: A Cost-Performance Analysis of Fact-Based Memory vs. Long-Context LLMs for Persistent Agents. arXiv 2603.04814. 2026. https://arxiv.org/html/2603.04814v1
33. Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks. arXiv 2602.16313. 2026. https://arxiv.org/html/2602.16313v1
34. Quantifying Frontier LLM Capabilities for Container Sandbox Escape. arXiv preprint (UK AI Security Institute). 2026. https://arxiv.org/html/2603.02277v3
35. Defeating Prompt Injections by Design. arXiv 2503.18813. 2025. https://arxiv.org/html/2503.18813v2
36. The Double Measurement Confound in Agent Benchmarks:De-Scaffolding, Ground-Truth Scoring, and Reliability Beyond the Mean. arXiv 2609.09218. 2026. https://arxiv.org/html/2609.09218v1
37. Towards Long-Horizon Agents: A Survey. OpenReview (submission). n.d.. https://openreview.net/pdf?id=HyhfhlbWGh

## How this survey was produced

This survey was written by a research harness. It planned the outline. A researcher with tools then searched for scholarly sources and read 37 pages into typed notes, section by section. The harness chose its follow-up searches from what had been read, built the organising framework from the notes and wrote each section from excerpts of the pages. Of 189 cited claims it checked, 189 are kept, each with a quote found on the page it cites, and 0 were removed. A referee pass by the model judged the draft: revise. A person approved the outline before any source was read and the paper before it was published. It is not peer-reviewed. Generated 2026-11-23T15:40:16+00:00.

### What the referee still found missing

- intro: Empirical long-context degradation work, e.g. Lost in the Middle and RULER, to ground the context-rot claim
- intro: Mainstream agent benchmarks (SWE-bench, WebArena, OSWorld, Terminal-Bench) as the setting for harness-versus-model claims
- intro: Prior agent surveys, to position this survey's contribution
- background: Function-calling APIs (OpenAI, Anthropic) and the Model Context Protocol specification as definitional anchors
- background: Code-as-action (CodeAct) as an alternative tool-call representation
- background: Generative Agents and Voyager as early agent memory and skill-library designs
- background: Container and microVM isolation technologies (gVisor, Firecracker) used for sandbox definitions
- framework: Justification of the four responsibilities against existing taxonomies (CoALA, agent design-pattern catalogues), and a check of whether the taxonomy is exhaustive or mutually exclusive
- framework: Production harnesses such as Claude Code, Codex CLI, Aider and Cursor as worked examples mapped onto the taxonomy
- framework: Permission and approval systems (human-in-the-loop confirmation) as a limit-enforcement mechanism
- loop_tools: Tree-search and reflection loops (LATS, Reflexion as a loop-control mechanism, Tree of Thoughts)
- loop_tools: ReWOO and other plan-then-execute designs as comparators to LLMCompiler