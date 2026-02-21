# sqlfp benchmarks

## bench 1
hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect oracle --rounds 100 " \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect oracle --rounds 100"
21.75x

hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect postgresql --rounds 100 " \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect postgresql --rounds 100"
16.49x

hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect mysql --rounds 100 " \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect mysql --rounds 100"
20.84x

hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect sqlite --rounds 100 " \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect sqlite --rounds 100"
18.63x

hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect mssql --rounds 100 " \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect mssql --rounds 100"
17.62x

hyperfine --warmup 3 \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlfp --dialect all --rounds 100 --orm" \
  "python benchs/bench_sqlfp_vs_sqlglot.py --engine sqlglot --dialect all --rounds 100 --orm"
20.44x
