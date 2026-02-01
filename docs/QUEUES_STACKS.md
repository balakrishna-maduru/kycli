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
