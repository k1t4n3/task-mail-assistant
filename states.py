from aiogram.fsm.state import StatesGroup, State

class AuthStates(StatesGroup):
    WAIT_PASSWORD = State()

class TaskStates(StatesGroup):
    WAIT_TEXT = State()
    WAIT_CONFIRM = State()
    WAIT_CANCEL_SELECT = State()