## services/stats.py

This module computes summary statistics for analytics rollup jobs, providing functions for calculating the average and percentage.

The specific problem in this module lies within the `percent` function. It performs integer division (`part // whole`) before multiplying by 100. This results in incorrect percentage calculations for many valid inputs. For instance, `percent(1, 4)` will incorrectly return `0` instead of `25`, because `1 // 4` evaluates to `0` due to integer truncation. The calculation should use floating-point division to maintain precision before converting to an integer or rounding as appropriate, or the multiplication by 100 should occur before the division.