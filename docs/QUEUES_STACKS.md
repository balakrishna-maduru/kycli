# Queues, Stacks, and Typed Workspaces

`kycli` introduces **Typed Workspaces**, allowing you to optimize storage for specific data structures beyond simple Key-Value pairs. This enables high-performance Queues, Stacks, and Priority Queues with strict concurrency guarantees.

## Concepts

### Workspace Types
When creating a workspace, you can assign it a specific type. This type enforces strict behavior and isolates commands to prevent errors (e.g., you cannot `kypop` from a Key-Value store).

| Type | Description | Best For |
| :--- | :--- | :--- |
| **KV** (Default) | Standard Key-Value store. | Caching, Config, User Sessions |
| **Queue** | FIFO (First-In-First-Out). | Job processing, Message passing |
| **Stack** | LIFO (Last-In-First-Out). | Undo history, DFS algorithms |
| **Priority Queue** | Ordered by priority (Highest first). | Task scheduling, Triage systems |

### Atomic Guarantees
All Queue/Stack operations (`push`, `pop`) are **Atomic** and use `BEGIN IMMEDIATE` transaction locking. This ensures:
- **Zero Duplicates**: Multiple consumers will never pop the same item.
- **Zero Data Loss**: Pop operations are transactional; if a script crashes mid-pop, the data remains (unless successfully committed).
- **Thread Safety**: Safe for concurrent use across threads (via shared instance) or processes (via SQLite locking).

---

## Usage Guide

### 1. Creating a Typed Workspace
Use the `--type` flag when creating a workspace.

```bash
# Create a Queue
kyws create my_queue --type queue

# Switch to it
kyuse my_queue
```

### 2. Queue Operations (FIFO)
Queues add items to the tail and remove from the head.

**How it works:**
- Each `kypush` writes an item into the queue table.
- `kypeek` reads the next item without removing it.
- `kypop` removes the next item in FIFO order (oldest first).

```bash
# Push items (No key needed!)
kypush "process_image_1.jpg"
kypush "process_image_2.jpg"

# Peek at the next item without removing
kypeek
# Output: process_image_1.jpg

# Pop item (Removes from DB)
kypop
# Output: process_image_1.jpg
```

### 3. Stack Operations (LIFO)
Stacks add to the top and remove from the top.

**How it works:**
- `kypush` adds a new item to the top of the stack.
- `kypop` removes the most recently pushed item.

```bash
kyws create my_stack --type stack
kyuse my_stack

kypush "step1"
kypush "step2"

kypop
# Output: step2
```

### 4. Priority Queues
Items with **higher priority number** are popped first.

**How it works:**
- Each `kypush` stores the item plus its priority.
- `kypop` returns the highest priority first; ties are FIFO by insertion order.

```bash
kyws create my_triage --type priority_queue
kyuse my_triage

kypush "low_task" --priority 10
kypush "URGENT_TASK" --priority 100

kypop
# Output: URGENT_TASK
```

### 5. Managing the Workspace

**Count Items:**
```bash
kycount
# Output: 42
```

**Clear Workspace:**
Warning: This permanently deletes all items in the workspace.
```bash
kyclear
```

---

## End-to-End Example (Queue Worker)

**Producer** (enqueue jobs):
```bash
kyws create jobs --type queue
kyuse jobs

kypush "resize:img_001.jpg"
kypush "resize:img_002.jpg"
kypush "resize:img_003.jpg"
```

**Consumer** (process jobs):
```bash
while true; do
    job=$(kypop)
    if [ "$job" = "None" ] || [ -z "$job" ]; then
        break
    fi
    echo "processing $job"
done
```

**Inspect queue depth:**
```bash
kycount
```

---

## Python API Integration

You can use `Kycore` directly in your Python applications for high-performance embeddable queues.

```python
from kycli import Kycore

# Initialize (Type is persisted on disk)
q = Kycore("my_queue.db")
q.set_type("queue")

# Producer
q.push({"task": "email", "id": 123})

# Consumer (Thread-Safe)
item = q.pop()
if item:
    print(f"Processing: {item}")
```

### Concurrency
To share a queue between threads, pass the `Kycore` instance or use a properly configured shared connection.
`kypush` and `kypop` utilize SQLite's atomic locking, making `kycli` a robust alternative to Redis/RabbitMQ for single-node setups.

---

## Planned Queue Features (Roadmap)

These are upcoming improvements for typed workspaces. They are **not implemented yet**, but are planned and tracked in the roadmap.

### 1. Batch Queue Ops
Increase throughput for large workloads.

**Proposed behavior:**
- `kypush --file` reads one item per line and enqueues them in order.
- `kypop --n` returns a newline-delimited batch in FIFO/LIFO/priority order.

```bash
# Push a batch of items from file (one item per line)
kypush --file tasks.txt

# Pop N items at once
kypop --n 100
```

### 2. Delayed Jobs
Schedule items to become visible after a delay.

**Proposed behavior:**
- Jobs are stored with `available_at` timestamp.
- `kypop` ignores items not yet visible.

```bash
kypush "email:user_123" --delay 30s
```

### 3. Visibility Timeout (Lease + Retry)
Allow consumers to lease work items with retry flows.

**Proposed behavior:**
- `kypop --lease` returns a `receipt_id` for ack/nack.
- If not acked within lease duration, the item becomes visible again.
- `kynack` can requeue with backoff or move to a dead-letter queue.

```bash
# Lease an item for 30 seconds
kypop --lease 30s

# Acknowledge completion
kyack <receipt_id>

# Re-queue the item for retry
kynack <receipt_id>
```

### 4. Workspace TTL Policies
Set default TTL for all new items in a workspace.

**Proposed behavior:**
- `kyttl set` stores a workspace-level default TTL.
- `kypush` and `kys` inherit TTL unless overridden.

```bash
kyttl set 7d
kyttl get
```

---

## Known Gaps (Not Implemented Yet)

- No batch queue operations (`--file`, `--n`).
- No delayed jobs or scheduled dequeue.
- No visibility timeout, `kyack`, or `kynack` flow.
- No per-workspace default TTL policies.
