from src.classes.directed_acyclic_graph import DirectedAcyclicGraph
from src.classes.node import Node
from src.classes.contract_program import ContractProgram
from src.profiles.generator import Generator
from src.tests.test import Test
from os.path import exists

if __name__ == "__main__":
    BUDGET = 10
    INSTANCES = 5
    TIME_LIMIT = BUDGET
    STEP_SIZE = 0.1
    QUALITY_INTERVAL = .05
    VERBOSE = False

    # Create a DAG manually for testing
    # Leaf nodes
    node_4 = Node(4, [], [], expression_type="contract")

    # Conditional Node
    node_3 = Node(3, [node_4], [], expression_type="conditional")

    # Intermediate nodes
    node_1 = Node(1, [node_3], [], expression_type="contract")
    node_2 = Node(2, [node_3], [], expression_type="contract")

    # Root node
    root = Node(0, [node_1, node_2], [], expression_type="contract")

    # Add the children
    node_1.children = [root]
    node_2.children = [root]
    node_3.children = [node_1, node_2]
    node_4.children = [node_3]

    # Nodes
    nodes = [root, node_1, node_2, node_3, node_4]

    # Create and verify the DAG from the node list
    dag = DirectedAcyclicGraph(nodes, root)

    # Used to create the synthetic data as instances and a populous file
    generate = True
    if not exists("populous.json") or generate:
        # Initialize a generator
        generator = Generator(INSTANCES, program_dag=dag, time_limit=TIME_LIMIT, step_size=STEP_SIZE, uniform_low=.05,
                              uniform_high=.9)

        # Let the root be trivial and not dependent on parents
        # generator.trivial_root = True

        # Adjust the DAG structure that has conditionals for generation
        generator.generator_dag = generator.adjust_dag_with_conditionals(dag)

        # Initialize the velocities for the quality mappings in a list
        # Need to initialize it after adjusting dag
        # A higher number x indicates a higher velocity in f(x)=1-e^{-x*t}
        # Note that the numbers can't be too small; otherwise the qualities converge to 0, giving a 0 utility
        generator.manual_override = [.1, .1, .1, "conditional", 10000]

        # Generate the nodes' quality mappings
        nodes = generator.generate_nodes()  # Return a list of file names of the nodes

        # populate the nodes' quality mappings into one populous file
        generator.populate(nodes, "populous.json")

    # Create the program with some budget

    program = ContractProgram(dag, BUDGET, scale=10**6, decimals=3, time_interval=1)

    # Adjust allocations (hardcode)
    test = Test(program)

    # Print the tree
    # print(test.print_tree(dag.root))

    # Test a random distribution on the initial allocations
    # print(test.test_initial_allocations(iterations=500, initial_is_random=True, verbose=False))

    # Test initial vs optimal expected utility and allocations
    test.find_utility_and_allocations(initial_allocation="uniform", verbose=False)
    test.find_utility_and_allocations(initial_allocation="Dirichlet", verbose=False)
