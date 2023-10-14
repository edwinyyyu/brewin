from brewparse import parse_program
from element import Element
from intbase import InterpreterBase, ErrorType


class Interpreter(InterpreterBase):
    builtin_functions = {"print", "inputi"}

    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output

        self.variables = {}

    def run(self, program):
        program_node = parse_program(program)

        functions = program_node.get("functions")
        self.function_defs = {function.get("name"): function for function in functions}

        main_function = Element("fcall", name="main", args=[])
        self.run_function(main_function)

    def run_function(self, function):
        name = function.get("name")
        args = function.get("args")

        if name in self.function_defs:
            function_def = self.function_defs[name]
            for statement in function_def.get("statements"):
                self.run_statement(statement)
        elif name in self.builtin_functions:
            return self.run_builtin(function)
        else:
            self.error(ErrorType.NAME_ERROR, f"No {name}() function was found")

    def run_builtin(self, function):
        name = function.get("name")
        args = function.get("args")

        match name:
            case "print":
                self.output(
                    "".join(
                        str(self.evaluate_expression(arg).get("val")) for arg in args
                    )
                )
            case "inputi":
                if len(args) == 1:
                    self.output(self.evaluate_expression(args[0]).get("val"))
                elif len(args) > 1:
                    self.error(
                        ErrorType.NAME_ERROR,
                        "No inputi() function found that takes > 1 parameter",
                    )
                return Element("int", val=int(self.get_input()))

    def run_statement(self, statement):
        match statement.elem_type:
            case "=":
                self.run_assignment(statement)
            case "fcall":
                self.run_function(statement)

    def run_assignment(self, assignment):
        name = assignment.get("name")
        expression = assignment.get("expression")
        self.variables[name] = self.evaluate_expression(expression)

    def evaluate_expression(self, expression):
        match expression.elem_type:
            case "+" | "-":
                return self.evaluate_binary_operation(expression)
            case "fcall":
                return self.run_function(expression)
            case "var":
                name = expression.get("name")
                if name in self.variables:
                    return self.variables[name]
                else:
                    self.error(
                        ErrorType.NAME_ERROR, f"Variable {name} has not been defined"
                    )
            case "int" | "string":
                return expression

    def evaluate_binary_operation(self, operation):
        op1 = self.evaluate_expression(operation.get("op1"))
        op2 = self.evaluate_expression(operation.get("op2"))
        if op1.elem_type == "string" or op2.elem_type == "string":
            self.error(
                ErrorType.TYPE_ERROR, "Incompatible types for arithmetic operation"
            )

        match operation.elem_type:
            case "+":
                return Element(op1.elem_type, val=op1.get("val") + op2.get("val"))
            case "-":
                return Element(op1.elem_type, val=op1.get("val") - op2.get("val"))
