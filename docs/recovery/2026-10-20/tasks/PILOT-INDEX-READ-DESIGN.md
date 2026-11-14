# Expected size and one extra byte

Use the regular file size already measured on the admitted descriptor. Allow one
extra byte to witness growth. Refuse a different byte count, a file beyond the
existing limit, or a changed identity by the existing rules. For the Git index
copy, also require the opened descriptor's size to agree with its named stat.

Drive each public reader with a small real file and record its peak Python
allocation. In race cases change the actual file after fstat and before read,
using the final bytes' digest so a hash mismatch cannot mask an accepted race.
