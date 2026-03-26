import arc_agi
from arc_agi import OperationMode
from arcengine import GameAction


def main():
    arc = arc_agi.Arcade(operation_mode=OperationMode.OFFLINE)
    env = arc.make("ls20", render_mode="terminal")

    # Take a few actions
    for _ in range(10):
        env.step(GameAction.ACTION1)

    print(arc.get_scorecard())
