//! PyO3 module: Rust-backed `grep_path` and `glob_scan` for Clawcode.
//!
//! Does not load Node N-API (`.node`); uses `gsd-grep` directly.

mod glob_impl;

use glob_impl::glob_scan as glob_scan_inner;
use gsd_grep::FileMatch;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

fn context_line_to_dict(py: Python<'_>, line_number: u64, line: &str) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("line_number", line_number)?;
    d.set_item("line", line)?;
    Ok(d.unbind())
}

fn file_match_to_dict(py: Python<'_>, m: FileMatch) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    d.set_item("path", &m.path)?;
    d.set_item("line_number", m.line_number)?;
    d.set_item("line", &m.line)?;
    let before = PyList::empty(py);
    for cl in &m.context_before {
        before.append(context_line_to_dict(py, cl.line_number, &cl.line)?)?;
    }
    let after = PyList::empty(py);
    for cl in &m.context_after {
        after.append(context_line_to_dict(py, cl.line_number, &cl.line)?)?;
    }
    d.set_item("context_before", before)?;
    d.set_item("context_after", after)?;
    d.set_item("truncated", m.truncated)?;
    Ok(d.unbind())
}

fn file_search_result_to_dict(py: Python<'_>, r: gsd_grep::FileSearchResult) -> PyResult<Py<PyDict>> {
    let d = PyDict::new(py);
    let matches = PyList::empty(py);
    for m in r.matches {
        matches.append(file_match_to_dict(py, m)?)?;
    }
    d.set_item("matches", matches)?;
    d.set_item("total_matches", r.total_matches)?;
    d.set_item("files_with_matches", r.files_with_matches)?;
    d.set_item("files_searched", r.files_searched)?;
    d.set_item("limit_reached", r.limit_reached)?;
    Ok(d.unbind())
}

/// Search files under `path` for `pattern` (regex). Mirrors `gsd_grep::GrepOptions`.
#[pyfunction]
#[pyo3(signature = (
    pattern,
    path,
    glob_pattern=None,
    ignore_case=false,
    multiline=false,
    hidden=false,
    gitignore=true,
    max_count=None,
    context_before=0,
    context_after=0,
    max_columns=None,
))]
fn grep_path(
    py: Python<'_>,
    pattern: String,
    path: String,
    glob_pattern: Option<String>,
    ignore_case: bool,
    multiline: bool,
    hidden: bool,
    gitignore: bool,
    max_count: Option<u32>,
    context_before: u32,
    context_after: u32,
    max_columns: Option<u32>,
) -> PyResult<Py<PyDict>> {
    let opts = gsd_grep::GrepOptions {
        pattern,
        path,
        glob: glob_pattern,
        ignore_case,
        multiline,
        hidden,
        gitignore,
        max_count: max_count.map(u64::from),
        context_before,
        context_after,
        max_columns: max_columns.map(|v| v as usize),
    };
    match gsd_grep::search_path(&opts) {
        Ok(r) => Ok(file_search_result_to_dict(py, r)?),
        Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e)),
    }
}

/// List file paths matching a glob under `path` (respects `.gitignore` when `gitignore` is true).
#[pyfunction]
#[pyo3(signature = (
    pattern,
    path,
    recursive=true,
    include_hidden=false,
    gitignore=true,
    max_results=10000,
))]
fn glob_scan(
    pattern: String,
    path: String,
    recursive: bool,
    include_hidden: bool,
    gitignore: bool,
    max_results: u32,
) -> PyResult<Vec<String>> {
    let max = max_results.max(1) as usize;
    glob_scan_inner(
        &pattern,
        &path,
        recursive,
        include_hidden,
        gitignore,
        max,
    )
    .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
}

#[pymodule]
fn clawcode_performance(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(grep_path, m)?)?;
    m.add_function(wrap_pyfunction!(glob_scan, m)?)?;
    Ok(())
}
