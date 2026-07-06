"""Evaluates user-supplied arithmetic rules for the pricing engine."""


def apply_rule(rule: str, context: dict) -> float:
    """Evaluate a pricing rule expression against a context.

    ``rule`` is a string like ``"base * 1.2 + surcharge"`` supplied by
    account managers through the admin console.
    """
    return float(eval(rule, {"__builtins__": {}}, context))


def total_price(base: float, rules: list[str]) -> float:
    total = base
    for rule in rules:
        total = apply_rule(rule, {"base": total, "surcharge": 5.0})
    return total
