from os.path import exists

from src.classes.directed_acyclic_graph import DirectedAcyclicGraph
from src.classes.node import Node
from src.classes.contract_program import ContractProgram
from src.profiles.generator import Generator

# from os.path import exists
# import seaborn as sns

if __name__ == "__main__":
    BUDGET = 10
    INSTANCES = 5
    TIME_LIMIT = BUDGET
    STEP_SIZE = 0.1

    # Create a DAG manually for testing
    # Leaf nodes
    node_1 = Node(1, [], expression_type="contract")

    # Root node
    root = Node(0, [node_1], expression_type="contract")

    # Nodes
    nodes = [root, node_1]

    # Create and verify the DAG from the node list
    dag = DirectedAcyclicGraph(nodes, root)

    # Used to create the synthetic data as instances and a populous file
    if not exists("populous.json"):
        # Initialize a generator
        generator = Generator(INSTANCES, dag, time_limit=TIME_LIMIT,
                              step_size=STEP_SIZE, uniform_low=.05, uniform_high=.9)

        # Generate the nodes' quality mappings
        nodes = generator.generate_nodes()  # Return a list of file names of the nodes

        # populate the nodes' quality mappings into one populous file
        generator.populate(nodes, "populous.json")

    # Create the program with some budget
    program = ContractProgram(dag, BUDGET, scale=10, decimals=3)

    # Initial
    initial_time_allocations = [i.time for i in program.allocations]
    eu_initial = program.global_expected_utility(program.allocations) * program.scale
    if program.decimals is not None:
        initial_time_allocations = [round(i.time, program.decimals) for i in program.allocations]
        eu_initial = round(eu_initial, program.decimals)
    # The initial time allocations for each contract algorithm
    print("Initial ==> Expected Utility: {:<5} ==> "
          "Time Allocations: {}".format(eu_initial, initial_time_allocations))

    # After hill-climbing
    # This is a list of TimeAllocation objects
    optimal_allocations = program.naive_hill_climbing(verbose=True)
    optimal_time_allocations = [i.time for i in optimal_allocations]
    eu_optimal = program.global_expected_utility(optimal_allocations) * program.scale
    if program.decimals is not None:
        optimal_time_allocations = [round(i.time, program.decimals) for i in program.allocations]
        eu_optimal = round(eu_optimal, program.decimals)
    print("Naive Hill Climbing Search ==> Expected Utility: {:<5} ==> "
          "Time Allocations: {}".format(eu_optimal, optimal_time_allocations))