#!/usr/bin/env python3
"""Apply a conservative Python docstring convention pass."""

from __future__ import annotations

import argparse
import ast
import inspect
from pathlib import Path

from docstring_parser import DocstringStyle, RenderingStyle, compose, parse
from docstring_parser.common import (
    Docstring,
    DocstringParam,
    DocstringRaises,
    DocstringReturns,
)


def should_skip_function_doc(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return whether a function should be skipped for docstring augmentation."""
    name = node.name

    if name.startswith("__") and name.endswith("__"):
        return True

    logger_prefixes = (
        "log_",
        "logger_",
    )
    logger_names = {
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "exception",
        "critical",
        "trace",
        "log",
    }
    if name in logger_names or name.startswith(logger_prefixes):
        return True

    body = list(node.body)
    if not body:
        return True

    first_idx = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        first_idx = 1

    effective_body = body[first_idx:]
    if not effective_body:
        return True

    if len(effective_body) == 1:
        stmt = effective_body[0]

        if isinstance(stmt, ast.Pass):
            return True

        if isinstance(stmt, ast.Raise):
            return True

        if isinstance(stmt, ast.Return):
            value = stmt.value

            if value is None:
                return True

            if isinstance(value, (ast.Constant, ast.Name, ast.Attribute)):
                return True

            if isinstance(value, ast.Call):
                return True

            if isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
                return True

        if isinstance(stmt, ast.Expr):
            value = stmt.value
            if isinstance(value, ast.Call):
                return True
            if isinstance(value, ast.Await) and isinstance(value.value, ast.Call):
                return True

    if len(effective_body) == 2:
        first, second = effective_body

        if isinstance(first, ast.Assign) and isinstance(second, ast.Return):
            if isinstance(second.value, (ast.Name, ast.Attribute)):
                return True

    return False


def annotation_to_str(node: ast.AST | None) -> str:
    """
    Return string representation of an annotation node.



    Parameters
    ----------
    node : ast.AST | None
        DOC_MISSING:param:node

    Returns
    -------
    str
        DOC_MISSING:return
    """
    if node is None:
        return "Any"
    try:
        return ast.unparse(node)
    except Exception:
        return "Any"


def indent_text(text: str, indent: str) -> str:
    """
    Indent multiline text with the provided prefix.



    Parameters
    ----------
    text : str
        DOC_MISSING:param:text
    indent : str
        DOC_MISSING:param:indent

    Returns
    -------
    str
        DOC_MISSING:return
    """
    return "\n".join((indent + line) if line else line for line in text.splitlines())


def collect_raises(fn: ast.AST) -> list[str]:
    """
    Collect unique raised exception names in a callable node.



    Parameters
    ----------
    fn : ast.AST
        DOC_MISSING:param:fn

    Returns
    -------
    list[str]
        DOC_MISSING:return
    """
    names: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call):
            exc = exc.func
        if isinstance(exc, ast.Name):
            names.append(exc.id)
        elif isinstance(exc, ast.Attribute):
            names.append(exc.attr)
        else:
            names.append("Exception")

    out: list[str] = []
    for name in names:
        if name not in out:
            out.append(name)
    return out


def should_skip(path: Path, excludes: list[str]) -> bool:
    """
    Return True if path should be excluded.



    Parameters
    ----------
    path : Path
        DOC_MISSING:param:path
    excludes : list[str]
        DOC_MISSING:param:excludes

    Returns
    -------
    bool
        DOC_MISSING:return
    """
    p = path.as_posix().lower()
    return any(f"/{ex.lower().strip('/')}/" in p for ex in excludes)


def extract_signature_params(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[str, str, bool]]:
    """
    Return parameters from a function signature as name, type, optional.



    Parameters
    ----------
    node : ast.FunctionDef | ast.AsyncFunctionDef
        DOC_MISSING:param:node

    Returns
    -------
    list[tuple[str, str, bool]]
        DOC_MISSING:return
    """
    params: list[tuple[str, str, bool]] = []

    posonlyargs = list(getattr(node.args, "posonlyargs", []))
    all_pos_args = posonlyargs + list(node.args.args)

    defaults_offset = len(all_pos_args) - len(node.args.defaults)
    defaults_map: dict[int, ast.expr] = {}
    for idx, default in enumerate(node.args.defaults):
        defaults_map[defaults_offset + idx] = default

    for idx, arg in enumerate(all_pos_args):
        if arg.arg in {"self", "cls"}:
            continue
        params.append((arg.arg, annotation_to_str(arg.annotation), idx in defaults_map))

    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        if arg.arg in {"self", "cls"}:
            continue
        params.append((arg.arg, annotation_to_str(arg.annotation), default is not None))

    if node.args.vararg and node.args.vararg.arg:
        params.append(
            (
                f"*{node.args.vararg.arg}",
                annotation_to_str(node.args.vararg.annotation),
                False,
            )
        )

    if node.args.kwarg and node.args.kwarg.arg:
        params.append(
            (
                f"**{node.args.kwarg.arg}",
                annotation_to_str(node.args.kwarg.annotation),
                False,
            )
        )

    return params


def extract_class_attributes(node: ast.ClassDef) -> list[tuple[str, str]]:
    """
    Return annotated class attributes.



    Parameters
    ----------
    node : ast.ClassDef
        DOC_MISSING:param:node

    Returns
    -------
    list[tuple[str, str]]
        DOC_MISSING:return
    """
    attrs: list[tuple[str, str]] = []
    for class_item in node.body:
        if isinstance(class_item, ast.AnnAssign) and isinstance(
            class_item.target, ast.Name
        ):
            attrs.append(
                (class_item.target.id, annotation_to_str(class_item.annotation))
            )
    return attrs


def normalize_docstring(doc: Docstring, fallback_summary: str) -> None:
    """
    Ensure docstring has a short description.



    Parameters
    ----------
    doc : Docstring
        DOC_MISSING:param:doc
    fallback_summary : str
        DOC_MISSING:param:fallback_summary
    """
    short = (doc.short_description or "").strip()
    if not short:
        doc.short_description = fallback_summary


def has_section(doc: str, name: str) -> bool:
    """Return whether a docstring section header is present."""
    lines = doc.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() != name:
            continue
        if idx + 1 >= len(lines):
            return True
        underline = lines[idx + 1].strip()
        if underline and set(underline) == {"-"}:
            return True
        return True
    return False


def is_trivial_docstring(doc: str) -> bool:
    """Return True if docstring is explicitly marked as trivial."""
    if not doc:
        return False

    lines = [line.strip() for line in doc.strip().splitlines() if line.strip()]
    if not lines:
        return False

    return lines[0].startswith("TRIVIAL")


def collapse_blank_lines(text: str) -> str:
    """Collapse multiple blank lines into a single blank line."""
    lines = text.splitlines()
    out = []
    prev_blank = False

    for line in lines:
        is_blank = not line.strip()
        if is_blank and prev_blank:
            continue
        out.append(line)
        prev_blank = is_blank

    return "\n".join(out)


def normalize_section_underline_lengths(doc: str) -> str:
    """Normalize NumPy-style section underline lengths."""
    section_names = {"Parameters", "Returns", "Raises", "Attributes"}
    lines = doc.splitlines()
    out: list[str] = []
    idx = 0

    while idx < len(lines):
        line = lines[idx]
        out.append(line)

        if line.strip() in section_names and idx + 1 < len(lines):
            next_line = lines[idx + 1]
            stripped = next_line.strip()
            if stripped and set(stripped) == {"-"}:
                indent = next_line[: len(next_line) - len(next_line.lstrip())]
                out.append(indent + ("-" * len(line.strip())))
                idx += 2
                continue

        idx += 1

    return "\n".join(out)


def build_function_doc(
    node: ast.FunctionDef | ast.AsyncFunctionDef, old_doc: str
) -> str:
    """Build updated docstring for a function or method."""
    old_doc = inspect.cleandoc(old_doc)
    normalized_old_doc = normalize_section_underline_lengths(old_doc)
    parsed = parse(normalized_old_doc)
    normalize_docstring(parsed, "Document function behavior.")

    has_params_section = has_section(normalized_old_doc, "Parameters")
    has_returns_section = has_section(normalized_old_doc, "Returns")
    has_raises_section = has_section(normalized_old_doc, "Raises")

    signature_params = extract_signature_params(node)
    signature_param_map = {
        name: (typ, optional) for name, typ, optional in signature_params
    }

    documented_params = {
        p.arg_name for p in parsed.params if getattr(p, "arg_name", None)
    }

    placeholder_param_descriptions = {"", "Description."}
    for param in parsed.params:
        if not getattr(param, "arg_name", None):
            continue
        if (param.description or "").strip() in placeholder_param_descriptions:
            param.description = f"DOC_MISSING:param:{param.arg_name}"
        if (
            not getattr(param, "type_name", None)
            and param.arg_name in signature_param_map
        ):
            typ, optional = signature_param_map[param.arg_name]
            param.type_name = typ
            param.is_optional = optional

    if not has_params_section:
        for name, typ, optional in signature_params:
            if name in documented_params:
                continue
            parsed.meta.append(
                DocstringParam(
                    args=["param", name],
                    description=f"DOC_MISSING:param:{name}",
                    arg_name=name,
                    type_name=typ,
                    is_optional=optional,
                    default=None,
                )
            )

    if node.returns is not None:
        ret_ann = annotation_to_str(node.returns)
        has_returns = ret_ann not in {"None", "NoneType"}
    else:
        ret_ann = None
        has_returns = False

    returns_meta = next(
        (meta for meta in parsed.meta if isinstance(meta, DocstringReturns)),
        None,
    )

    placeholder_return_descriptions = {
        "",
        "Description.",
        "Description of the returned value.",
    }

    if has_returns:
        if returns_meta is None and not has_returns_section:
            parsed.meta.append(
                DocstringReturns(
                    args=["returns"],
                    description="DOC_MISSING:return",
                    type_name=ret_ann,
                    is_generator=False,
                    return_name=None,
                )
            )
        elif returns_meta is not None:
            if (
                returns_meta.description or ""
            ).strip() in placeholder_return_descriptions:
                returns_meta.description = "DOC_MISSING:return"
            if not getattr(returns_meta, "type_name", None):
                returns_meta.type_name = ret_ann

    documented_raises = {
        meta.type_name
        for meta in parsed.meta
        if isinstance(meta, DocstringRaises) and meta.type_name
    }

    placeholder_raise_descriptions = {
        "",
        "Description.",
        "Condition under which it is raised.",
    }
    for meta in parsed.meta:
        if (
            isinstance(meta, DocstringRaises)
            and (meta.description or "").strip() in placeholder_raise_descriptions
        ):
            type_name = meta.type_name or "Exception"
            meta.description = f"DOC_MISSING:raises:{type_name}"

    if not has_raises_section:
        for raise_name in collect_raises(node):
            if raise_name in documented_raises:
                continue
            parsed.meta.append(
                DocstringRaises(
                    args=["raises", raise_name],
                    description=f"DOC_MISSING:raises:{raise_name}",
                    type_name=raise_name,
                )
            )

    return collapse_blank_lines(
        compose(
            parsed,
            style=DocstringStyle.NUMPYDOC,
            rendering_style=RenderingStyle.COMPACT,
        ).rstrip()
    )


def build_class_doc(node: ast.ClassDef, old_doc: str) -> str:
    """Build updated docstring for a class."""
    old_doc = inspect.cleandoc(old_doc)
    normalized_old_doc = normalize_section_underline_lengths(old_doc)

    lines = normalized_old_doc.strip().splitlines()
    summary = lines[0].strip() if lines else "Document class behavior."
    ext = "\n".join(line.rstrip() for line in lines[1:]).strip()

    attrs = extract_class_attributes(node)

    chunks = [summary]

    if ext:
        chunks.extend(["", ext])

    # If Attributes already exists, preserve it exactly as-is.
    if has_section(normalized_old_doc, "Attributes"):
        return collapse_blank_lines("\n".join(chunks).rstrip())

    if attrs:
        chunks.extend(["", "Attributes", "----------"])
        for name, typ in attrs:
            chunks.append(f"{name} : {typ}")
            chunks.append(f"    DOC_MISSING:attr:{name}")

    return collapse_blank_lines("\n".join(chunks).rstrip())


def process_file(path: Path, write: bool = True) -> tuple[int, str | None]:
    """Apply docstring pass to a single file and return updated count and content."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0, None

    lines = source.splitlines()
    replacements: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef)
        ) and should_skip_function_doc(node):
            continue
        if not node.body:
            continue

        first = node.body[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            continue

        old_doc = first.value.value

        if is_trivial_docstring(old_doc):
            continue
        if isinstance(node, ast.ClassDef):
            new_doc = build_class_doc(node, old_doc)
        else:
            new_doc = build_function_doc(node, old_doc)

        if new_doc == old_doc:
            continue

        start = first.lineno - 1
        end = first.end_lineno - 1
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        block = (
            indent + '"""' + "\n" + indent_text(new_doc, indent) + "\n" + indent + '"""'
        )
        replacements.append((start, end, block))

    if not replacements:
        return 0, None

    new_lines = lines[:]
    replacements.sort(key=lambda item: item[0], reverse=True)
    for start, end, block in replacements:
        new_lines[start : end + 1] = block.splitlines()

    new_source = "\n".join(new_lines) + ("\n" if source.endswith("\n") else "")

    if new_source == source:
        return 0, None

    if write:
        path.write_text(new_source, encoding="utf-8")

    return len(replacements), new_source


def main() -> int:
    """
    Run CLI entrypoint.

    Returns
    -------
    int
        DOC_MISSING:return

    Raises
    ------
    SystemExit
        DOC_MISSING:raises:SystemExit
    """
    import difflib

    parser = argparse.ArgumentParser(
        description="Run docstring convention pass on Python files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="File or directory to process (default: current directory).",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=["tests", "alembic"],
        help="Path segment to exclude. Can be repeated.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Show unified diff instead of writing files.",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        raise SystemExit(f"Invalid path: {root}")

    if root.is_file():
        if root.suffix != ".py":
            raise SystemExit(f"Invalid Python file: {root}")
        paths = [root]
    else:
        paths = list(root.rglob("*.py"))

    changed_files = 0
    changed_docstrings = 0

    for path in paths:
        if should_skip(path, args.exclude):
            continue

        original = path.read_text(encoding="utf-8")
        updated, new_source = process_file(path, write=not args.diff)
        if not updated:
            continue

        changed_files += 1
        changed_docstrings += updated

        if args.diff and new_source is not None:
            diff = difflib.unified_diff(
                original.splitlines(keepends=True),
                new_source.splitlines(keepends=True),
                fromfile=str(path),
                tofile=str(path),
            )
            print("".join(diff), end="")

    print(f"changed_files={changed_files}")
    print(f"changed_docstrings={changed_docstrings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
