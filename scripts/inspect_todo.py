"""Inspect installed HA todo API for signature verification."""
import inspect
import re

from homeassistant.components import todo
from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)

print("TodoItem fields:", list(TodoItem.__dataclass_fields__))
print("Feature members:", [m for m in dir(TodoListEntityFeature) if m.isupper()])
print("Status members:", [m for m in dir(TodoItemStatus) if m.isupper()])
src = inspect.getsource(todo.TodoListEntity)
print("methods:", sorted(re.findall(r"async def (async_\w+)", src)))
for name in (
    "async_set_todo_item_due_date",
    "async_set_todo_item_description",
    "async_update_todo_item",
    "async_create_todo_item",
    "async_set_todo_item_status",
    "async_delete_todo_item",
):
    print(name, inspect.signature(getattr(todo.TodoListEntity, name)))

# state attributes written by the component
m = re.search(r"ATTR_ITEMS? = .+", src)
comp_src = inspect.getsource(todo)
for line in comp_src.splitlines():
    if "_ATTR_" in line or "items" in line and "= " in line:
        pass
print("ATTR names:", [n for n in dir(todo) if n.startswith("ATTR")])
