"""Recursive-descent parser for SHDL (shdl.md §13).

One token of lookahead everywhere except one documented spot: telling a
replication ``8{sign}`` apart from a name-template substitution ``fa{i}``
inside a concatenation uses a bounded scan to the matching ``}`` (see
:meth:`Parser._parse_concat_item`).

Context legality (shdl.md §7.4: declaration-context generator bodies hold
declarations, connection-context bodies hold connections) is enforced
structurally at parse time, so even never-emitted `when` branches must be
well-formed for their context (§14).
"""

from __future__ import annotations

from .ast_nodes import (
    Arg,
    BinOp,
    BoolAnd,
    BoolExpr,
    BoolOr,
    Cmp,
    Component,
    Concat,
    ConcatItem,
    Conditional,
    Connection,
    ConstantDecl,
    Expr,
    GenItem,
    Generator,
    Import,
    IndexBit,
    IndexSlice,
    InitAssign,
    InstanceDecl,
    Module,
    Name,
    NameTemplate,
    Num,
    Param,
    PortDecl,
    Primary,
    RangeAB,
    RangeItem,
    RangeN,
    RangeOpen,
    RangeTo,
    Replication,
    Signal,
)
from .diagnostics import ErrorCode, err
from .lexer import T, Token, lex
from .source import SourceFile

DECL_CONTEXT = "declaration"
CONN_CONTEXT = "connection"


class Parser:
    def __init__(self, src: SourceFile):
        result = lex(src)
        self.tokens = result.tokens
        self.doc_comment = result.doc_comment
        self.src = src
        self.i = 0

    # -- token helpers ------------------------------------------------------

    @property
    def cur(self) -> Token:
        return self.tokens[self.i]

    def peek(self, offset: int = 1) -> Token:
        j = min(self.i + offset, len(self.tokens) - 1)
        return self.tokens[j]

    def advance(self) -> Token:
        tok = self.cur
        if tok.kind is not T.EOF:
            self.i += 1
        return tok

    def expect(self, kind: T, what: str | None = None) -> Token:
        if self.cur.kind is not kind:
            expected = what or kind.value
            raise err(
                ErrorCode.E0201,
                f"expected {expected}, found {self.cur}",
                self.cur.pos,
            )
        return self.advance()

    def expect_keyword(self, word: str) -> Token:
        if self.cur.kind is not T.KEYWORD or self.cur.text != word:
            raise err(
                ErrorCode.E0201,
                f"expected '{word}', found {self.cur}",
                self.cur.pos,
            )
        return self.advance()

    def at_keyword(self, word: str) -> bool:
        return self.cur.kind is T.KEYWORD and self.cur.text == word

    # -- module -------------------------------------------------------------

    def parse_module(self, module_name: str) -> Module:
        imports: list[Import] = []
        while self.at_keyword("use"):
            imports.append(self._parse_import())
        components: list[Component] = []
        while self.cur.kind is not T.EOF:
            if self.at_keyword("use"):
                raise err(
                    ErrorCode.E0201,
                    "imports must precede all component definitions",
                    self.cur.pos,
                )
            components.append(self._parse_component())
        return Module(
            name=module_name,
            file=self.src.name,
            imports=tuple(imports),
            components=tuple(components),
            doc_comment=self.doc_comment,
            path=self.src.path,
        )

    def _parse_import(self) -> Import:
        start = self.expect_keyword("use")
        mod = self.expect(T.IDENT, "module name")
        self.expect(T.SCOPE)
        self.expect(T.LBRACE)
        names: list[tuple[str, Token]] = []
        while True:
            name_tok = self.expect(T.IDENT, "imported component name")
            names.append((name_tok.text, name_tok))
            if self.cur.kind is T.COMMA:
                self.advance()
                continue
            break
        self.expect(T.RBRACE)
        self.expect(T.SEMI)
        return Import(
            module=mod.text,
            module_pos=mod.pos,
            names=tuple((n, t.pos) for n, t in names),
            pos=start.pos,
        )

    # -- component ----------------------------------------------------------

    def _parse_component(self) -> Component:
        is_top = False
        start = self.cur
        if self.at_keyword("top"):
            self.advance()
            is_top = True
        self.expect_keyword("component")
        name = self.expect(T.IDENT, "component name")

        params: tuple[Param, ...] = ()
        if self.cur.kind is T.LT:
            params = self._parse_param_list()

        self.expect(T.LPAREN)
        inputs = self._parse_port_list()
        self.expect(T.RPAREN)
        self.expect(T.ARROW)
        self.expect(T.LPAREN)
        outputs = self._parse_port_list()
        self.expect(T.RPAREN)
        self.expect(T.LBRACE)

        decls: list[GenItem] = []
        init_blocks: list[tuple] = []
        connect_blocks: list[tuple] = []
        while self.cur.kind is not T.RBRACE:
            if self.at_keyword("connect"):
                connect_blocks.append(self._parse_connect_block())
            elif self.at_keyword("init"):
                init_blocks.append(self._parse_init_block())
            else:
                decls.append(self._parse_gen_item(DECL_CONTEXT))
        self.expect(T.RBRACE)

        return Component(
            name=name.text,
            params=params,
            inputs=inputs,
            outputs=outputs,
            decls=tuple(decls),
            init_blocks=tuple(init_blocks),
            connect_blocks=tuple(connect_blocks),
            is_top=is_top,
            pos=start.pos,
            file=self.src.name,
        )

    def _parse_param_list(self) -> tuple[Param, ...]:
        self.expect(T.LT)
        params: list[Param] = []
        while True:
            name = self.expect(T.IDENT, "parameter name")
            default: int | None = None
            if self.cur.kind is T.EQ:
                self.advance()
                default = self.expect(T.NUMBER, "parameter default value").value
            params.append(Param(name.text, default, name.pos))
            if self.cur.kind is T.COMMA:
                self.advance()
                continue
            break
        self.expect(T.GT)
        return tuple(params)

    def _parse_port_list(self) -> tuple[PortDecl, ...]:
        ports: list[PortDecl] = []
        if self.cur.kind is T.RPAREN:
            return ()
        while True:
            name = self.expect(T.IDENT, "port name")
            width: Expr | None = None
            if self.cur.kind is T.LBRACKET:
                self.advance()
                width = self._parse_arith()
                self.expect(T.RBRACKET)
            ports.append(PortDecl(name.text, width, name.pos))
            if self.cur.kind is T.COMMA:
                self.advance()
                continue
            break
        return tuple(ports)

    # -- blocks and items ----------------------------------------------------

    def _parse_connect_block(self) -> tuple:
        start = self.expect_keyword("connect")
        self.expect(T.LBRACE)
        items: list[GenItem] = []
        while self.cur.kind is not T.RBRACE:
            items.append(self._parse_gen_item(CONN_CONTEXT))
        self.expect(T.RBRACE)
        return (start.pos, tuple(items))

    def _parse_init_block(self) -> tuple:
        start = self.expect_keyword("init")
        self.expect(T.LBRACE)
        assigns: list[InitAssign] = []
        while self.cur.kind is not T.RBRACE:
            target = self._parse_primary()
            self.expect(T.EQ)
            value = self.expect(T.NUMBER, "init value")
            self.expect(T.SEMI)
            assigns.append(InitAssign(target, value.value, target.pos))
        self.expect(T.RBRACE)
        return (start.pos, tuple(assigns))

    def _parse_gen_item(self, context: str) -> GenItem:
        tok = self.cur
        if tok.kind is T.GT:
            return self._parse_generator(context)
        if self.at_keyword("when"):
            return self._parse_conditional(context)
        if context == DECL_CONTEXT:
            if tok.kind is T.IDENT:
                return self._parse_declaration()
            raise err(
                ErrorCode.E0604,
                f"expected an instance or constant declaration, found {tok}",
                tok.pos,
            )
        # connection context
        if tok.kind is T.IDENT or tok.kind is T.LBRACE:
            return self._parse_connection()
        raise err(
            ErrorCode.E0604,
            f"expected a connection, found {tok}",
            tok.pos,
        )

    def _parse_declaration(self) -> GenItem:
        name = self._parse_name_template()
        if self.cur.kind is T.COLON:
            self.advance()
            type_tok = self.expect(T.IDENT, "component type name")
            args: tuple[Arg, ...] = ()
            if self.cur.kind is T.LT:
                args = self._parse_arg_list()
            self.expect(T.SEMI)
            return InstanceDecl(name, type_tok.text, type_tok.pos, args, name.pos)
        if self.cur.kind in (T.LBRACKET, T.EQ):
            if not name.is_plain:
                raise err(
                    ErrorCode.E0201,
                    "a constant name must be a plain identifier (no substitutions)",
                    name.pos,
                )
            width: Expr | None = None
            if self.cur.kind is T.LBRACKET:
                self.advance()
                width = self._parse_arith()
                self.expect(T.RBRACKET)
            self.expect(T.EQ)
            value = self.expect(T.NUMBER, "constant value")
            self.expect(T.SEMI)
            return ConstantDecl(name.plain, width, value.value, name.pos)
        raise err(
            ErrorCode.E0201,
            f"expected ':' (instance) or '=' (constant) after name, found {self.cur}",
            self.cur.pos,
        )

    def _parse_arg_list(self) -> tuple[Arg, ...]:
        self.expect(T.LT)
        args: list[Arg] = []
        while True:
            start = self.cur
            arg_name: str | None = None
            if start.kind is T.IDENT and self.peek().kind is T.EQ:
                self.advance()
                self.advance()
                arg_name = start.text
            expr = self._parse_arith()
            args.append(Arg(arg_name, expr, start.pos))
            if self.cur.kind is T.COMMA:
                self.advance()
                continue
            break
        self.expect(T.GT)
        return tuple(args)

    def _parse_generator(self, context: str) -> Generator:
        start = self.expect(T.GT)
        var = self.expect(T.IDENT, "generator variable")
        self.expect(T.LBRACKET)
        ranges: list[RangeItem] = [self._parse_range_item()]
        while self.cur.kind is T.COMMA:
            self.advance()
            ranges.append(self._parse_range_item())
        self.expect(T.RBRACKET)
        body = self._parse_brace_body(context)
        return Generator(var.text, var.pos, tuple(ranges), body, start.pos)

    def _parse_range_item(self) -> RangeItem:
        start = self.cur
        if start.kind is T.COLON:  # [:b]
            self.advance()
            hi = self._parse_arith()
            return RangeTo(hi, start.pos)
        lo = self._parse_arith()
        if self.cur.kind is T.COLON:
            self.advance()
            if self.cur.kind in (T.RBRACKET, T.COMMA):  # [a:]
                return RangeOpen(lo, start.pos)
            hi = self._parse_arith()
            return RangeAB(lo, hi, start.pos)
        return RangeN(lo, start.pos)

    def _parse_conditional(self, context: str) -> Conditional:
        start = self.expect_keyword("when")
        self.expect(T.LBRACE)
        cond = self._parse_bool()
        self.expect(T.RBRACE)
        then_body = self._parse_brace_body(context)
        else_body: tuple[GenItem, ...] = ()
        if self.at_keyword("else"):
            self.advance()
            else_body = self._parse_brace_body(context)
        return Conditional(cond, then_body, else_body, start.pos)

    def _parse_brace_body(self, context: str) -> tuple[GenItem, ...]:
        self.expect(T.LBRACE)
        items: list[GenItem] = []
        while self.cur.kind is not T.RBRACE:
            items.append(self._parse_gen_item(context))
        self.expect(T.RBRACE)
        return tuple(items)

    # -- connections and signals ----------------------------------------------

    def _parse_connection(self) -> Connection:
        src = self._parse_signal()
        self.expect(T.ARROW)
        dst = self._parse_signal()
        self.expect(T.SEMI)
        return Connection(src, dst, src.pos)

    def _parse_signal(self) -> Signal:
        if self.cur.kind is T.LBRACE:
            return self._parse_concat()
        return self._parse_primary()

    def _parse_concat(self) -> Concat:
        start = self.expect(T.LBRACE)
        items: list[ConcatItem] = [self._parse_concat_item()]
        while self.cur.kind is T.COMMA:
            self.advance()
            items.append(self._parse_concat_item())
        self.expect(T.RBRACE)
        return Concat(tuple(items), start.pos)

    def _parse_concat_item(self) -> ConcatItem:
        tok = self.cur
        if tok.kind is T.NUMBER:
            # A bare number can only start a replication: N{ ... }.
            count = self._parse_arith()
            return self._parse_replication_group(count, tok)
        if tok.kind is T.IDENT and self.peek().kind is T.LBRACE:
            # Ambiguity (documented deviation from pure 1-token lookahead):
            # `fa{i}` is a name-template substitution; `N{a.O, b}` would be a
            # replication with an identifier count. We scan the brace group:
            # if its contents form a single arithmetic expression, we read the
            # whole thing as a name template (the overwhelmingly common case,
            # e.g. `fa{i}` inside a generator); otherwise (a comma, dot,
            # index, or nested group — things only signals contain) it is a
            # replication. Replication counts are conventionally literals
            # (`8{sign}`); an identifier count over a *single-identifier*
            # group must be disambiguated by the author, e.g. via a generator.
            if not self._brace_group_is_single_arith(self.i + 1):
                count = self._parse_arith()
                return self._parse_replication_group(count, tok)
        return self._parse_primary()

    def _parse_replication_group(self, count: Expr, start: Token) -> Replication:
        self.expect(T.LBRACE)
        items: list[ConcatItem] = [self._parse_concat_item()]
        while self.cur.kind is T.COMMA:
            self.advance()
            items.append(self._parse_concat_item())
        self.expect(T.RBRACE)
        return Replication(count, tuple(items), start.pos)

    def _brace_group_is_single_arith(self, open_idx: int) -> bool:
        """True if the brace group starting at token index ``open_idx`` holds a
        single arithmetic expression (NUMBER/IDENT/+-*/ and nested braces only)."""
        assert self.tokens[open_idx].kind is T.LBRACE
        depth = 0
        j = open_idx
        arith_kinds = (T.NUMBER, T.IDENT, T.PLUS, T.MINUS, T.STAR, T.SLASH)
        while j < len(self.tokens):
            kind = self.tokens[j].kind
            if kind is T.LBRACE:
                depth += 1
            elif kind is T.RBRACE:
                depth -= 1
                if depth == 0:
                    return True
            elif kind is T.EOF:
                return False
            elif kind not in arith_kinds:
                return False
            j += 1
        return False

    def _parse_primary(self) -> Primary:
        base = self._parse_name_template()
        port: NameTemplate | None = None
        if self.cur.kind is T.DOT:
            self.advance()
            port = self._parse_name_template()
        index = None
        if self.cur.kind is T.LBRACKET:
            self.advance()
            index = self._parse_index()
            self.expect(T.RBRACKET)
        return Primary(base, port, index, base.pos)

    def _parse_index(self):
        if self.cur.kind is T.COLON:  # [:b]
            self.advance()
            hi = self._parse_arith()
            return IndexSlice(None, hi)
        lo = self._parse_arith()
        if self.cur.kind is T.COLON:
            self.advance()
            if self.cur.kind is T.RBRACKET:  # [a:]
                return IndexSlice(lo, None)
            hi = self._parse_arith()
            return IndexSlice(lo, hi)
        return IndexBit(lo)

    def _parse_name_template(self) -> NameTemplate:
        first = self.expect(T.IDENT, "identifier")
        parts: list[str | Expr] = [first.text]
        while self.cur.kind is T.LBRACE:
            self.advance()
            parts.append(self._parse_arith())
            self.expect(T.RBRACE)
            if self.cur.kind is T.IDENT:
                parts.append(self.advance().text)
        return NameTemplate(tuple(parts), first.pos)

    # -- expressions -----------------------------------------------------------

    def _parse_arith(self) -> Expr:
        left = self._parse_term()
        while self.cur.kind in (T.PLUS, T.MINUS):
            op = self.advance()
            right = self._parse_term()
            left = BinOp(op.text, left, right, left.pos)
        return left

    def _parse_term(self) -> Expr:
        left = self._parse_factor()
        while self.cur.kind in (T.STAR, T.SLASH):
            op = self.advance()
            right = self._parse_factor()
            left = BinOp(op.text, left, right, left.pos)
        return left

    def _parse_factor(self) -> Expr:
        tok = self.cur
        if tok.kind is T.NUMBER:
            self.advance()
            return Num(tok.value, tok.pos)
        if tok.kind is T.IDENT:
            self.advance()
            return Name(tok.text, tok.pos)
        if tok.kind is T.LBRACE:
            self.advance()
            inner = self._parse_arith()
            self.expect(T.RBRACE)
            return inner
        raise err(
            ErrorCode.E0201,
            f"expected a number, identifier, or '{{expr}}', found {tok}",
            tok.pos,
        )

    def _parse_bool(self) -> BoolExpr:
        items = [self._parse_bool_and()]
        while self.cur.kind is T.OROR:
            self.advance()
            items.append(self._parse_bool_and())
        if len(items) == 1:
            return items[0]
        return BoolOr(tuple(items), items[0].pos)

    def _parse_bool_and(self) -> BoolExpr:
        items = [self._parse_cmp()]
        while self.cur.kind is T.ANDAND:
            self.advance()
            items.append(self._parse_cmp())
        if len(items) == 1:
            return items[0]
        return BoolAnd(tuple(items), items[0].pos)

    _RELOPS = {
        T.EQEQ: "==",
        T.NE: "!=",
        T.LT: "<",
        T.LE: "<=",
        T.GT: ">",
        T.GE: ">=",
    }

    def _parse_cmp(self) -> BoolExpr:
        if self.cur.kind is T.LPAREN:
            self.advance()
            inner = self._parse_bool()
            self.expect(T.RPAREN)
            return inner
        left = self._parse_arith()
        op_tok = self.cur
        if op_tok.kind not in self._RELOPS:
            raise err(
                ErrorCode.E0201,
                f"expected a relational operator, found {op_tok}",
                op_tok.pos,
            )
        self.advance()
        right = self._parse_arith()
        return Cmp(left, self._RELOPS[op_tok.kind], right, left.pos)


def parse_source(src: SourceFile, module_name: str) -> Module:
    return Parser(src).parse_module(module_name)
