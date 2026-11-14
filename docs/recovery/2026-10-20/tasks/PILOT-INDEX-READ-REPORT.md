# First-commit readers reserve memory in proportion to the admitted file

Both public paths accepted the same 48 bytes with a peak traced allocation under
13 KiB on Windows Python 3.12.14. Baseline `f180fcc`, TASK/DESIGN `de90a37`,
product and regressions `8ecce6d`.

| Operation on a real 48-byte file | Peak bytes before | Peak bytes after |
| --- | ---: | ---: |
| Read the stored install bytes and verify their digest | 33,566,423 | 12,103 |
| Reuse an existing identical private index copy | 33,565,967 | 11,150 |

One process measured each operation with tracemalloc active only during the read.
The ceiling remained 32 MiB. Both readers request the observed size plus one to
detect growth and compare the returned byte count to the admitted size. The index
copy also checks that the opened file still agrees with its named size.

The first eight focused cases gave 4 failures and 4 passes before the change.
The final nine cases pass, including the added check for a file that grows
past the limit between the named and opened stats. The seven single-change
mutants each failed the relevant test: restoring either ceiling-sized read,
accepting short or long reads in either reader, removing agreement between
named and opened size, and removing either existing size ceiling.

The first-commit supersede module passed all 67 cases in both UTF-8 and CP1251.
The snapshot, records, lock and final regression modules gave 163 passes and
5 skips in each encoding. Four optional cases require the older Git reader and
one requires permission to create a symbolic link. No model calls or full
matrix runs were made. These measurements establish the excessive allocation;
the separate generic store refusal from the original run remains unexplained.
