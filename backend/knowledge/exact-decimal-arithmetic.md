---
title: Exact decimal arithmetic in JavaScript apps (calculators, money)
url: https://floating-point-gui.de/
topic: floating point, decimals, calculators, money
verified: 2026-10-25
stack: javascript, typescript, node, react, vite

---
JavaScript numbers are IEEE 754 double-precision binary floating point, so most decimal fractions cannot be stored
exactly: 0.1 + 0.2 evaluates to 0.30000000000000004. Rounding only for display hides the error in simple cases but
errors can still accumulate across operations.

Options for exact decimal results: keep amounts as integers of the smallest unit (cents) when the number of decimals
is fixed; or use an arbitrary-precision decimal library such as big.js (small, decimal arithmetic with configurable
rounding: https://mikemcl.github.io/big.js/) or decimal.js (larger, adds functions such as trigonometry and
logarithms). Format the result for the user with Intl.NumberFormat or the library's toFixed / toString.

Test the edge cases explicitly: 0.1 + 0.2, division by zero, very large and very small numbers, negative zero,
repeated operations, and the rounding mode the app promises.
