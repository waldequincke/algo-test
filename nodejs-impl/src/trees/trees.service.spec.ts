import { ConfigService } from '@nestjs/config';
import { Test, TestingModule } from '@nestjs/testing';
import { TreeProcessingException } from '../infrastructure/tree-processing.exception';
import { TreeNodeDto } from './dto/tree-node.dto';
import { TreesService } from './trees.service';

function node(value: number, left?: TreeNodeDto, right?: TreeNodeDto): TreeNodeDto {
  const n = new TreeNodeDto();
  n.value = value;
  n.left = left;
  n.right = right;
  return n;
}

describe('TreesService', () => {
  let service: TreesService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TreesService,
        {
          provide: ConfigService,
          useValue: {
            get: (key: string, defaultValue: number) => defaultValue,
          },
        },
      ],
    }).compile();

    service = module.get(TreesService);
  });

  describe('solveLevelOrder', () => {
    it('should return a single level for a leaf node', () => {
      expect(service.solveLevelOrder(node(42))).toEqual([[42]]);
    });

    it('should return level-order traversal for a 3-node tree', () => {
      //     1
      //    / \
      //   2   3
      const result = service.solveLevelOrder(node(1, node(2), node(3)));
      expect(result).toEqual([[1], [2, 3]]);
    });

    it('should handle a right-skewed tree', () => {
      //  1 → 2 → 3
      const result = service.solveLevelOrder(node(1, undefined, node(2, undefined, node(3))));
      expect(result).toEqual([[1], [2], [3]]);
    });

    it('should handle a left-skewed tree', () => {
      //      3
      //     /
      //    2
      //   /
      //  1
      const result = service.solveLevelOrder(node(3, node(2, node(1))));
      expect(result).toEqual([[3], [2], [1]]);
    });

    it('should handle a complete binary tree of 4 levels', () => {
      //            1
      //          /   \
      //        2       3
      //       / \     / \
      //      4   5   6   7
      const result = service.solveLevelOrder(
        node(1,
          node(2, node(4), node(5)),
          node(3, node(6), node(7)),
        ),
      );
      expect(result).toEqual([[1], [2, 3], [4, 5, 6, 7]]);
    });

    it('should use default value=0 when node has no value', () => {
      const n = new TreeNodeDto(); // value defaults to 0
      expect(service.solveLevelOrder(n)).toEqual([[0]]);
    });

    it('should throw TreeProcessingException when depth exceeds maxDepth (500)', () => {
      let deep = node(501);
      for (let i = 500; i >= 1; i--) deep = node(i, deep);

      expect(() => service.solveLevelOrder(deep)).toThrow(TreeProcessingException);
      expect(() => service.solveLevelOrder(deep)).toThrow(
        /Tree depth exceeds security limits/,
      );
    });

    it('should succeed exactly at maxDepth (500 levels)', () => {
      let deep = node(500);
      for (let i = 499; i >= 1; i--) deep = node(i, undefined, deep);

      const result = service.solveLevelOrder(deep);
      expect(result).toHaveLength(500);
    });

    it('should throw TreeProcessingException when node count exceeds maxNodes (10 000)', () => {
      // Build a service with maxNodes=3 for easy testing
      const smallService = new TreesService({
        get: (key: string, def: number) => (key === 'TREE_MAX_NODES' ? 3 : def),
      } as unknown as ConfigService);

      //     1
      //    / \
      //   2   3
      //      / \
      //     4   5   ← level 3 adds 2 nodes → totalNodes = 3+2 = 5 > 3
      const tree = node(1, node(2), node(3, node(4), node(5)));

      expect(() => smallService.solveLevelOrder(tree)).toThrow(TreeProcessingException);
      expect(() => smallService.solveLevelOrder(tree)).toThrow(
        /Tree node count exceeds security limits/,
      );
    });
  });
});
