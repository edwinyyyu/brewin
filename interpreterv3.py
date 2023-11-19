from copy import deepcopy

from brewparse import parse_program
from element import Element
from intbase import InterpreterBase, ErrorType


class Variable:
    def __init__(self, element):
        super().__init__()
        self.element = element


class Return(Exception):
    def __init__(self, value):
        super().__init__()
        self.value = value


class Interpreter(InterpreterBase):
    builtin_functions = {"print", "inputi", "inputs"}

    def __init__(self, console_output=True, inp=None, trace_output=False):
        super().__init__(console_output, inp)
        self.trace_output = trace_output

        self.function_defs = {}
        self.variables = {}
        self.scopes = []

    def run(self, program):
        program_node = parse_program(program)
        functions = program_node.get("functions")
        for function in functions:
            name = function.get("name")
            params = function.get("args")
            self.function_defs.setdefault(name, {})
            self.function_defs[name][len(params)] = function

        main_function = Element("fcall", name="main", args=[])
        self.run_function(main_function)

    def run_statement(self, statement):
        match statement.elem_type:
            case "if":
                self.run_if(statement)
            case "while":
                self.run_while(statement)
            case "return":
                self.run_return(statement)
            case "fcall":
                self.run_function(statement)
            case "=":
                self.run_assignment(statement)

    def create_scope(self):
        self.scopes.append(set())

    def delete_scope(self):
        for variable_name in self.scopes[-1]:
            self.pop_variable(variable_name)
        self.scopes.pop()

    def push_variable(self, variable_name, variable):
        self.scopes[-1].add(variable_name)
        self.variables.setdefault(variable_name, [])
        self.variables[variable_name].append(variable)

    def pop_variable(self, variable_name):
        self.variables[variable_name].pop()
        if not self.variables[variable_name]:
            del self.variables[variable_name]

    def run_if(self, if_block):
        statements = if_block.get("statements")
        else_statements = if_block.get("else_statements")
        self.create_scope()
        try:
            condition = self.to_bool(if_block.get("condition"))
            if condition.get("val"):
                for statement in statements:
                    self.run_statement(statement)
            elif else_statements:
                for statement in else_statements:
                    self.run_statement(statement)
        except TypeError:
            self.error(
                ErrorType.TYPE_ERROR, "If condition does not evaluate to a boolean"
            )
        finally:
            self.delete_scope()

    def run_while(self, while_block):
        statements = while_block.get("statements")
        self.create_scope()
        try:
            while True:
                condition = self.to_bool(while_block.get("condition"))
                if condition.get("val"):
                    for statement in statements:
                        self.run_statement(statement)
                else:
                    break
        except TypeError:
            self.error(
                ErrorType.TYPE_ERROR, "While condition does not evaluate to a boolean"
            )
        finally:
            self.delete_scope()

    def run_return(self, statement):
        expression = statement.get("expression")
        if expression:
            raise Return(deepcopy(self.evaluate_expression(expression)))
        else:
            raise Return(Element("nil"))

    def run_function(self, function):
        name = function.get("name")
        args = function.get("args")
        if name in self.function_defs and len(args) in self.function_defs[name]:
            function_def = self.function_defs[name][len(args)]
            params = function_def.get("args")
            statements = function_def.get("statements")
        elif name in self.variables:
            function_def = self.variables[name][-1].element
            params = function_def.get("args")
            statements = function_def.get("statements")

            if function_def.elem_type not in {"func", "closure"}:
                self.error(
                    ErrorType.TYPE_ERROR, f"Variable {name} does not hold a function"
                )
            if len(params) != len(args):
                self.error(
                    ErrorType.TYPE_ERROR,
                    f"{name} takes {len(params)} parameters: {len(args)} arguments given",
                )
        elif name in self.builtin_functions:
            return self.run_builtin(function)
        else:
            self.error(
                ErrorType.NAME_ERROR,
                f"No {name}() function found that takes {len(args)} parameters",
            )

        param_names = {param.get("name") for param in params}

        # Get arguments before shadowing
        arg_variables = []
        for param, arg in zip(params, args):
            param_name = param.get("name")
            arg_name = arg.get("name")
            if param.elem_type == "refarg" and arg_name in self.variables:
                arg_variables.append(self.variables[arg_name][-1])
            elif param.elem_type == "refarg" and arg_name in self.function_defs:
                arg_variables.append(Variable(self.evaluate_expression(arg)))
            else:
                arg_variables.append(Variable(deepcopy(self.evaluate_expression(arg))))

        self.create_scope()
        if function_def.elem_type == "closure":
            captures = function_def.get("captures")
            exposed_captures = dict(
                filter(lambda capture: capture[0] not in param_names, captures.items())
            )
            for capture_name, capture_value in exposed_captures.items():
                self.push_variable(capture_name, Variable(capture_value))

        for param, arg_variable in zip(params, arg_variables):
            param_name = param.get("name")
            self.push_variable(param_name, arg_variable)

        try:
            for statement in statements:
                self.run_statement(statement)
            return Element("nil")
        except Return as ret:
            return ret.value
        finally:
            if function_def.elem_type == "closure":
                for capture_name in exposed_captures:
                    captures[capture_name] = self.variables[capture_name][-1].element

            self.delete_scope()

    def run_builtin(self, function):
        name = function.get("name")
        args = function.get("args")
        match name:
            case "print":
                self.output("".join(self.fmt(arg) for arg in args))
                return Element("nil")
            case "inputi":
                if len(args) == 1:
                    self.output(self.evaluate_expression(args[0]).get("val"))
                elif len(args) > 1:
                    self.error(
                        ErrorType.NAME_ERROR,
                        "No inputi() function found that takes > 1 parameter",
                    )
                return Element("int", val=int(self.get_input()))
            case "inputs":
                if len(args) == 1:
                    self.output(self.evaluate_expression(args[0]).get("val"))
                elif len(args) > 1:
                    self.error(
                        ErrorType.NAME_ERROR,
                        "No inputs() function found that takes > 1 parameter",
                    )
                return Element("string", val=self.get_input())

    def fmt(self, expression):
        element = self.evaluate_expression(expression)
        match element.elem_type:
            case "int" | "string":
                return str(element.get("val"))
            case "bool":
                return str(element.get("val")).lower()

    def to_bool(self, expression):
        element = self.evaluate_expression(expression)
        match element.elem_type:
            case "bool":
                return element
            case "int":
                return Element("bool", val=bool(element.get("val")))
            case _:
                raise TypeError

    def to_int(self, expression):
        element = self.evaluate_expression(expression)
        match element.elem_type:
            case "int":
                return element
            case "bool":
                return Element("int", val=int(element.get("val")))
            case _:
                raise TypeError

    def run_assignment(self, assignment):
        variable_name = assignment.get("name")
        expression = assignment.get("expression")
        if variable_name not in self.variables:
            self.push_variable(
                variable_name, Variable(self.evaluate_expression(expression))
            )
        else:
            self.variables[variable_name][-1].element = self.evaluate_expression(
                expression
            )

    def evaluate_expression(self, expression):
        match expression.elem_type:
            case "neg" | "!":
                return self.evaluate_unary_operation(expression)
            case "+" | "-" | "*" | "/" | "==" | "!=" | "<" | ">" | "<=" | ">=" | "||" | "&&":
                return self.evaluate_binary_operation(expression)
            case "fcall":
                return self.run_function(expression)
            case "lambda":
                captures = deepcopy(
                    {
                        name: values[-1].element
                        for name, values in self.variables.items()
                    }
                )
                return Element(
                    "closure",
                    args=expression.get("args"),
                    statements=expression.get("statements"),
                    captures=captures,
                )
            case "var":  # Includes named functions and bound lambdas
                name = expression.get("name")
                if name in self.variables:
                    return self.variables[name][-1].element
                elif name in self.function_defs:
                    if len(self.function_defs[name]) != 1:
                        self.error(
                            ErrorType.NAME_ERROR, f"{name}() function is ambiguous"
                        )
                    return next(iter(self.function_defs[name].values()))
                else:
                    self.error(
                        ErrorType.NAME_ERROR, f"Variable {name} has not been defined"
                    )
            case "int" | "string" | "bool" | "nil" | "func" | "closure":
                return expression

    def evaluate_unary_operation(self, operation):
        op1 = self.evaluate_expression(operation.get("op1"))
        try:
            match operation.elem_type:
                case "neg":
                    if op1.elem_type == "int":
                        return Element("int", val=-op1.get("val"))
                    else:
                        raise TypeError
                case "!":
                    op1 = self.to_bool(op1)
                    return Element("bool", val=not op1.get("val"))
        except TypeError:
            self.error(
                ErrorType.TYPE_ERROR,
                f"Incompatible type for operation {operation.elem_type}: {op1.elem_type}",
            )

    def evaluate_binary_operation(self, operation):
        # Strict evaluation
        op1 = self.evaluate_expression(operation.get("op1"))
        op2 = self.evaluate_expression(operation.get("op2"))
        try:
            match operation.elem_type:
                case "+":
                    if op1.elem_type == op2.elem_type == "string":
                        return Element("string", val=op1.get("val") + op2.get("val"))
                    op1 = self.to_int(op1)
                    op2 = self.to_int(op2)
                    return Element("int", val=op1.get("val") + op2.get("val"))
                case "-":
                    op1 = self.to_int(op1)
                    op2 = self.to_int(op2)
                    return Element("int", val=op1.get("val") - op2.get("val"))
                case "*":
                    op1 = self.to_int(op1)
                    op2 = self.to_int(op2)
                    return Element("int", val=op1.get("val") * op2.get("val"))
                case "/":
                    op1 = self.to_int(op1)
                    op2 = self.to_int(op2)
                    return Element("int", val=op1.get("val") // op2.get("val"))
                case "==":
                    if (op1.elem_type, op2.elem_type) in {
                        ("int", "bool"),
                        ("bool", "int"),
                    }:
                        op1 = self.to_bool(op1)
                        op2 = self.to_bool(op2)
                        return self.evaluate_binary_operation(
                            Element("==", op1=op1, op2=op2)
                        )
                    elif op1.elem_type != op2.elem_type:
                        return Element("bool", val=False)
                    elif op1.elem_type == "func" or op1.elem_type == "closure":
                        return Element("bool", val=op1 is op2)
                    else:
                        return Element("bool", val=op1.get("val") == op2.get("val"))
                case "!=":
                    if (op1.elem_type, op2.elem_type) in {
                        ("int", "bool"),
                        ("bool", "int"),
                    }:
                        op1 = self.to_bool(op1)
                        op2 = self.to_bool(op2)
                        return self.evaluate_binary_operation(
                            Element("!=", op1=op1, op2=op2)
                        )
                    elif op1.elem_type != op2.elem_type:
                        return Element("bool", val=True)
                    elif op1.elem_type == "func" or op1.elem_type == "closure":
                        return Element("bool", val=op1 is not op2)
                    else:
                        return Element("bool", val=op1.get("val") != op2.get("val"))
                case "<":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("bool", val=op1.get("val") < op2.get("val"))
                    else:
                        raise TypeError
                case ">":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("bool", val=op1.get("val") > op2.get("val"))
                    else:
                        raise TypeError
                case "<=":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("bool", val=op1.get("val") <= op2.get("val"))
                    else:
                        raise TypeError
                case ">=":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("bool", val=op1.get("val") >= op2.get("val"))
                    else:
                        raise TypeError
                case "||":
                    op1 = self.to_bool(op1)
                    op2 = self.to_bool(op2)
                    return Element("bool", val=op1.get("val") or op2.get("val"))
                case "&&":
                    op1 = self.to_bool(op1)
                    op2 = self.to_bool(op2)
                    return Element("bool", val=op1.get("val") and op2.get("val"))
        except TypeError:
            self.error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for operation {operation.elem_type}: {op1.elem_type} and {op2.elem_type}",
            )
