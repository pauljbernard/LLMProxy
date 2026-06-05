# Routing Policy Specification

## Purpose

The proxy must choose the best model for both the current task and the broader user session. Routing is a policy decision informed by cost, quality, latency, privacy, and historical outcomes.

## Routing Inputs

Every routing decision must consider request-level inputs:

- domain
- task type
- complexity
- privacy sensitivity
- tool-use requirement
- token budget estimate
- context-window requirement
- expected answer quality bar
- training value
- risk level

Every routing decision must also consider session-level inputs:

- session objective
- current workflow mode
- user preferences
- budget policy
- latency tolerance
- privacy mode
- prior turns in the session
- prior provider or model failures in the session
- user corrections or dissatisfaction signals
- repository or workspace context if available

## Routing Outputs

Each routing decision must produce:

- selected provider
- selected model
- selected routing mode
- ranked alternatives
- decision rationale
- predicted cost class
- predicted latency class
- fallback plan

## Required Routing Modes

- local_only
- frontier_single
- frontier_ensemble
- local_then_frontier
- frontier_then_local
- judge_only
- record_only

`teacher_single` and `teacher_ensemble` may remain as implementation aliases, but policy documents should use `frontier_single` and `frontier_ensemble` as the clearer semantic names.

## Ranking Factors

The proxy must rank candidate models using a weighted policy that can incorporate:

- domain benchmark score
- task-type benchmark score
- session satisfaction history
- recent provider-health score
- cost per task estimate
- latency estimate
- context-window sufficiency
- privacy compatibility
- tool support compatibility
- operator priority rules

## Session-Aware Policy Requirements

The routing layer must support:

- sticky preference for a high-performing model within a session when appropriate
- override when health, price, or quality thresholds are breached
- escalation from local to frontier when local confidence is too low
- de-escalation from frontier to local when local specialists are sufficient
- stricter policy for high-risk domains such as investment analysis
- local-first policy for privacy-sensitive sessions

## Decision Logging

For each routed request, the proxy must persist:

- session identifier
- ranked candidate list
- selected model and provider
- features used in the decision
- policy version
- fallback events
- eventual outcome signals

## Evaluation of Routing Quality

Routing quality must be measured by:

- answer quality by route
- cost by route
- latency by route
- fallback frequency
- user retry rate
- user correction rate
- frontier-to-local substitution success rate
- local specialist win rate against designated frontier baselines

## Minimum Acceptable Behavior

The routing system is acceptable only if:

1. it can choose between local and multiple frontier providers
2. it can justify the choice in stored metadata
3. it adapts when providers degrade or policy inputs change
4. it improves cost efficiency without unacceptable quality loss
