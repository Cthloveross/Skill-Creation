#!/usr/bin/env python3
"""Solve a small, explicitly specified linear system from JSON stdin.

Input schema:
{
  "variables": ["x", "y"],
  "equations": [
    {"coefficients": {"x": 1, "y": -1}, "rhs": 2}
  ],
  "tolerance": 1e-12
}
Each equation means sum(coefficients[name] * name) = rhs.
"""
import json
import math
import sys


def emit(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, allow_nan=False))
    raise SystemExit(code)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        emit({"ok": False, "error": "stdin must contain JSON", "detail": str(exc)}, 1)
    if not isinstance(data, dict):
        emit({"ok": False, "error": "input must be an object"}, 1)
    variables = data.get("variables")
    equations = data.get("equations")
    tolerance = data.get("tolerance", 1e-12)
    if not isinstance(variables, list) or not variables or not all(isinstance(v, str) and v for v in variables):
        emit({"ok": False, "error": "variables must be a nonempty array of names"}, 1)
    if len(set(variables)) != len(variables):
        emit({"ok": False, "error": "variable names must be unique"}, 1)
    if not isinstance(equations, list) or not equations:
        emit({"ok": False, "error": "equations must be a nonempty array"}, 1)
    if not numeric(tolerance) or float(tolerance) <= 0:
        emit({"ok": False, "error": "tolerance must be a positive finite number"}, 1)
    eps = float(tolerance)
    index = {name: i for i, name in enumerate(variables)}
    matrix = []
    for eq_index, equation in enumerate(equations):
        if not isinstance(equation, dict) or not isinstance(equation.get("coefficients"), dict) or not numeric(equation.get("rhs")):
            emit({"ok": False, "error": "each equation needs coefficients object and numeric rhs", "equation": eq_index}, 1)
        row = [0.0] * len(variables)
        for name, coefficient in equation["coefficients"].items():
            if name not in index or not numeric(coefficient):
                emit({"ok": False, "error": "unknown variable or nonnumeric coefficient", "equation": eq_index, "variable": name}, 1)
            row[index[name]] = float(coefficient)
        row.append(float(equation["rhs"]))
        matrix.append(row)

    # Reduced row echelon form with partial pivoting.
    pivot_columns = []
    pivot_row = 0
    width = len(variables)
    for col in range(width):
        candidate = max(range(pivot_row, len(matrix)), key=lambda r: abs(matrix[r][col]), default=None)
        if candidate is None or abs(matrix[candidate][col]) <= eps:
            continue
        matrix[pivot_row], matrix[candidate] = matrix[candidate], matrix[pivot_row]
        divisor = matrix[pivot_row][col]
        matrix[pivot_row] = [value / divisor for value in matrix[pivot_row]]
        for row_index in range(len(matrix)):
            if row_index == pivot_row:
                continue
            factor = matrix[row_index][col]
            if abs(factor) > eps:
                matrix[row_index] = [a - factor * b for a, b in zip(matrix[row_index], matrix[pivot_row])]
        pivot_columns.append(col)
        pivot_row += 1
        if pivot_row == len(matrix):
            break

    for row in matrix:
        if all(abs(row[col]) <= eps for col in range(width)) and abs(row[width]) > eps:
            emit({"ok": False, "error": "system is inconsistent; no solution"}, 1)
    if len(pivot_columns) < width:
        free = [variables[col] for col in range(width) if col not in pivot_columns]
        emit({"ok": False, "error": "system is underdetermined; no unique solution", "free_variables": free}, 1)

    answer = [0.0] * width
    for row_index, col in enumerate(pivot_columns):
        answer[col] = matrix[row_index][width]
    # Normalize insignificant binary floating-point noise for readable output while
    # retaining substantially more precision than normal spreadsheet displays.
    answer = [0.0 if abs(value) <= eps else value for value in answer]
    residuals = []
    for equation in equations:
        lhs = sum(float(equation["coefficients"].get(name, 0)) * answer[i] for i, name in enumerate(variables))
        residuals.append(lhs - float(equation["rhs"]))
    emit({"ok": True, "solution": dict(zip(variables, answer)), "residuals": residuals})


if __name__ == "__main__":
    main()
