# ADR-0002: Start with transparent bounded learning updates

## Status
Accepted

## Decision
The first version will not use reinforcement learning. It will use bounded, inspectable feature-weight updates with these rules:

1. Explicit feedback has priority over implicit behaviour.
2. Implicit behaviour receives a smaller multiplier.
3. One event cannot change a preference by more than 0.08.
4. Hard constraints cannot be silently changed by behaviour.
5. Every inferred preference stores source, confidence, and recency.
6. Users can review, correct, delete, or reset learned preferences.
7. Exploration remains part of recommendation generation to avoid filter bubbles.

## Consequences
The learning system is easier to debug, evaluate, and explain before enough outcome data exists for learning-to-rank or contextual bandits.
