from brewparse import parse_program
from element import Element
from intbase import InterpreterBase, ErrorType


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
        self.scopes.append([])

    def delete_scope(self):
        for variable_name in self.scopes[-1]:
            self.variables[variable_name].pop()
            if not self.variables[variable_name]:
                del self.variables[variable_name]
        self.scopes.pop()

    def run_if(self, if_block):
        statements = if_block.get("statements")
        else_statements = if_block.get("else_statements")

        condition = self.evaluate_expression(if_block.get("condition"))
        if condition.elem_type != "bool":
            self.error(
                ErrorType.TYPE_ERROR, "If condition does not evaluate to a boolean"
            )

        self.create_scope()
        try:
            if condition.get("val"):
                for statement in statements:
                    self.run_statement(statement)
            elif else_statements:
                for statement in else_statements:
                    self.run_statement(statement)
        finally:
            self.delete_scope()

    def run_while(self, while_block):
        statements = while_block.get("statements")

        self.create_scope()
        try:
            while True:
                condition = self.evaluate_expression(while_block.get("condition"))
                if condition.elem_type != "bool":
                    self.error(
                        ErrorType.TYPE_ERROR,
                        "While condition does not evaluate to a boolean",
                    )

                if condition.get("val"):
                    for statement in statements:
                        self.run_statement(statement)
                else:
                    break
        finally:
            self.delete_scope()

    def run_return(self, statement):
        expression = statement.get("expression")
        if expression:
            raise Return(self.evaluate_expression(expression))
        else:
            raise Return(Element("nil"))

    def run_function(self, function):
        name = function.get("name")
        args = function.get("args")

        if name in self.function_defs and len(args) in self.function_defs[name]:
            function_def = self.function_defs[name][len(args)]
            params = function_def.get("args")
            statements = function_def.get("statements")

            for param, arg in zip(params, args):
                param_name = param.get("name")
                self.variables.setdefault(param_name, [])
                self.variables[param_name].append(self.evaluate_expression(arg))

            self.create_scope()
            try:
                for statement in statements:
                    self.run_statement(statement)
                return Element("nil")
            except Return as ret:
                return ret.value
            finally:
                self.delete_scope()

                for param in params:
                    param_name = param.get("name")
                    self.variables[param_name].pop()

                    if not self.variables[param_name]:
                        del self.variables[param_name]
        elif name in self.builtin_functions:
            return self.run_builtin(function)
        else:
            self.error(
                ErrorType.NAME_ERROR,
                f"No {name}() function found that takes {len(args)} parameters",
            )

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

    def run_assignment(self, assignment):
        name = assignment.get("name")
        expression = assignment.get("expression")

        if name not in self.variables:
            self.scopes[-1].append(name)
            self.variables[name] = [self.evaluate_expression(expression)]
        else:
            self.variables[name][-1] = self.evaluate_expression(expression)

    def evaluate_expression(self, expression):
        match expression.elem_type:
            case "neg" | "!":
                return self.evaluate_unary_operation(expression)
            case "+" | "-" | "*" | "/" | "==" | "!=" | "<" | ">" | "<=" | ">=" | "||" | "&&":
                return self.evaluate_binary_operation(expression)
            case "fcall":
                return self.run_function(expression)
            case "var":
                name = expression.get("name")
                if name in self.variables:
                    return self.variables[name][-1]
                else:
                    self.error(
                        ErrorType.NAME_ERROR, f"Variable {name} has not been defined"
                    )
            case "int" | "string" | "bool" | "nil":
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
                    if op1.elem_type == "bool":
                        return Element("bool", val=not op1.get("val"))
                    else:
                        raise TypeError
        except:
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
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("int", val=op1.get("val") + op2.get("val"))
                    elif op1.elem_type == op2.elem_type == "string":
                        return Element("string", val=op1.get("val") + op2.get("val"))
                    else:
                        raise TypeError
                case "-":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("int", val=op1.get("val") - op2.get("val"))
                    else:
                        raise TypeError
                case "*":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("int", val=op1.get("val") * op2.get("val"))
                    else:
                        raise TypeError
                case "/":
                    if op1.elem_type == op2.elem_type == "int":
                        return Element("int", val=op1.get("val") // op2.get("val"))
                    else:
                        raise TypeError
                case "==":
                    if op1.elem_type != op2.elem_type:
                        return Element("bool", val=False)
                    else:
                        return Element("bool", val=op1.get("val") == op2.get("val"))
                case "!=":
                    if op1.elem_type != op2.elem_type:
                        return Element("bool", val=True)
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
                    if op1.elem_type == op2.elem_type == "bool":
                        return Element("bool", val=op1.get("val") or op2.get("val"))
                    else:
                        raise TypeError
                case "&&":
                    if op1.elem_type == op2.elem_type == "bool":
                        return Element("bool", val=op1.get("val") and op2.get("val"))
                    else:
                        raise TypeError
        except TypeError:
            self.error(
                ErrorType.TYPE_ERROR,
                f"Incompatible types for operation {operation.elem_type}: {op1.elem_type} and {op2.elem_type}",
            )
