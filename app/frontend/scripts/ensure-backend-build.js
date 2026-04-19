const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const repoRoot = path.resolve(__dirname, "..", "..", "..");
const distBinary = path.join(repoRoot, "dist", "eyecue-backend");
const buildStampPath = path.join(repoRoot, "dist", ".backend-build-stamp");

const watchRoots = [
  path.join(repoRoot, "app"),
];

const watchFiles = [
  path.join(repoRoot, "backend.spec"),
  path.join(repoRoot, "requirements.txt"),
  path.join(repoRoot, "build_backend.sh"),
];

const watchedExtensions = new Set([".py", ".spec", ".txt"]);

function getMtimeMs(filePath) {
  try {
    return fs.statSync(filePath).mtimeMs;
  } catch (_err) {
    return 0;
  }
}

function readBuildStamp() {
  try {
    const value = fs.readFileSync(buildStampPath, "utf8").trim();
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  } catch (_err) {
    return 0;
  }
}

function writeBuildStamp(sourceMtime) {
  fs.mkdirSync(path.dirname(buildStampPath), { recursive: true });
  fs.writeFileSync(buildStampPath, String(Math.max(Date.now(), sourceMtime)));
}

function walkLatestMtime(startPath) {
  let latest = 0;

  if (!fs.existsSync(startPath)) {
    return latest;
  }

  const stack = [startPath];
  while (stack.length > 0) {
    const current = stack.pop();
    const stat = fs.statSync(current);

    if (stat.isDirectory()) {
      if (current === path.join(repoRoot, "app", "frontend")) {
        continue;
      }
      const entries = fs.readdirSync(current, { withFileTypes: true });
      for (const entry of entries) {
        if (entry.name === "__pycache__" || entry.name.startsWith(".")) {
          continue;
        }
        stack.push(path.join(current, entry.name));
      }
      continue;
    }

    const ext = path.extname(current).toLowerCase();
    if (watchedExtensions.has(ext)) {
      latest = Math.max(latest, stat.mtimeMs);
    }
  }

  return latest;
}

function latestSourceMtime() {
  let latest = 0;

  for (const filePath of watchFiles) {
    latest = Math.max(latest, getMtimeMs(filePath));
  }

  for (const rootPath of watchRoots) {
    latest = Math.max(latest, walkLatestMtime(rootPath));
  }

  return latest;
}

function runBuild() {
  const result = spawnSync("bash", ["build_backend.sh"], {
    cwd: repoRoot,
    stdio: "inherit",
  });

  if (result.status !== 0) {
    process.exit(result.status || 1);
  }
}

function main() {
  const force = process.env.EYECUE_FORCE_BACKEND_BUILD === "1";
  const binaryExists = getMtimeMs(distBinary) > 0;
  const buildStamp = readBuildStamp();
  const sourceMtime = latestSourceMtime();

  if (!force && binaryExists && buildStamp >= sourceMtime) {
    console.log("[backend:build] Backend binary is up to date. Skipping rebuild.");
    return;
  }

  if (force) {
    console.log("[backend:build] Force rebuild requested.");
  } else if (!binaryExists) {
    console.log("[backend:build] Backend binary missing. Building now.");
  } else {
    console.log("[backend:build] Backend sources changed. Rebuilding.");
  }

  runBuild();
  writeBuildStamp(sourceMtime);
}

main();
