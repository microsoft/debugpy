---
name: numpy
description: Best practices for numerical computing with NumPy including arrays, broadcasting, and vectorization.
---

# Skill: NumPy

Best practices for numerical computing with NumPy including arrays, broadcasting, and vectorization.

## When to Use

Apply this skill when doing numerical computing with NumPy — arrays, broadcasting, linear algebra, random sampling.

## Arrays

-   Use explicit dtypes (`np.float64`, `np.int32`) when creating arrays.
-   Prefer `np.zeros`, `np.ones`, `np.empty`, `np.arange`, `np.linspace` over list-based construction.
-   Use structured arrays or separate arrays instead of object arrays.

## Vectorization

-   Replace Python loops with vectorized NumPy operations wherever possible.
-   Use broadcasting rules to operate on arrays of different shapes without explicit expansion.
-   Use `np.where()` for conditional element-wise operations.

## Memory

-   Use `np.float32` instead of `np.float64` when precision is not critical to halve memory.
-   Use views (`reshape`, slicing) instead of copies when data doesn't need mutation.
-   Use `np.memmap` for arrays too large to fit in RAM.

## Random

-   Use `np.random.default_rng(seed)` (new Generator API) instead of `np.random.seed()`.
-   Always seed random generators in tests for reproducibility.

## Pitfalls

-   Don't compare floats with `==`; use `np.allclose()` or `np.isclose()`.
-   Beware of silent integer overflow in integer arrays.
-   Avoid `np.matrix` — it's deprecated; use 2D `np.ndarray`.

