//! Simplified filesystem glob using `ignore` + `globset` (no N-API, no fs cache).

use globset::{GlobBuilder, GlobSet, GlobSetBuilder};
use ignore::WalkBuilder;
use std::path::{Path, PathBuf};

fn fix_unclosed_braces(pattern: String) -> String {
    let opens = pattern.chars().filter(|&c| c == '{').count();
    let closes = pattern.chars().filter(|&c| c == '}').count();
    if opens > closes {
        let mut fixed = pattern;
        for _ in 0..(opens - closes) {
            fixed.push('}');
        }
        fixed
    } else {
        pattern
    }
}

fn build_glob_pattern(glob: &str, recursive: bool) -> String {
    let normalized = glob.replace('\\', "/");
    let pattern = if !recursive || normalized.contains('/') || normalized.starts_with("**") {
        normalized
    } else {
        format!("**/{normalized}")
    };
    fix_unclosed_braces(pattern)
}

fn compile_glob(glob: &str, recursive: bool) -> Result<GlobSet, String> {
    let mut builder = GlobSetBuilder::new();
    let pattern = build_glob_pattern(glob, recursive);
    let g = GlobBuilder::new(&pattern)
        .literal_separator(true)
        .build()
        .map_err(|e| format!("Invalid glob pattern: {e}"))?;
    builder.add(g);
    builder
        .build()
        .map_err(|e| format!("Failed to build glob matcher: {e}"))
}

/// Walk `path` and return absolute paths of files matching `pattern`.
pub fn glob_scan(
    pattern: &str,
    path: &str,
    recursive: bool,
    include_hidden: bool,
    use_gitignore: bool,
    max_results: usize,
) -> Result<Vec<String>, String> {
    let pattern = pattern.trim();
    let pattern = if pattern.is_empty() { "*" } else { pattern };

    let root = Path::new(path);
    let root_canon = root
        .canonicalize()
        .map_err(|e| format!("Invalid path {path}: {e}"))?;

    let glob_set = compile_glob(pattern, recursive)?;

    let mut walk = WalkBuilder::new(&root_canon);
    walk.hidden(!include_hidden);
    walk.git_ignore(use_gitignore);
    walk.git_exclude(use_gitignore);
    walk.ignore(use_gitignore);
    walk.parents(use_gitignore);

    let mut out: Vec<String> = Vec::new();
    for entry in walk.build() {
        let entry = entry.map_err(|e| e.to_string())?;
        let p = entry.path();
        if !p.is_file() {
            continue;
        }
        let rel: PathBuf = match p.strip_prefix(&root_canon) {
            Ok(r) => r.to_path_buf(),
            Err(_) => continue,
        };
        let rel_str = rel.to_string_lossy().replace('\\', "/");
        if glob_set.is_match(rel_str.as_str()) {
            out.push(p.to_string_lossy().to_string());
            if out.len() >= max_results {
                break;
            }
        }
    }

    Ok(out)
}
