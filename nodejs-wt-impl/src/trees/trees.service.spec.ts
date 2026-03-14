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

describe('TreesService (Worker Threads)', () => {
  let service: TreesService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        TreesService,
        {
          provide: ConfigService,
          useValue: { get: (_key: string, defaultValue: number) => defaultValue },
        },
      ],
    }).compile();

    service = module.get(TreesService);
  });

  afterEach(async () => {
    await service.onModuleDestroy();
  });

  describe('solveLevelOrder', () => {
    it('should return a single level for a leaf node', async () => {
      expect(await service.solveLevelOrder(node(42))).toEqual([[42]]);
    });

    it('should return level-order traversal for a 3-node tree', async () => {
      //     1
      //    / \
      //   2   3
      const result = await service.solveLevelOrder(node(1, node(2), node(3)));
      expect(result).toEqual([[1], [2, 3]]);
    });

    it('should handle a right-skewed tree', async () => {
      const result = await service.solveLevelOrder(
        node(1, undefined, node(2, undefined, node(3))),
      );
      expect(result).toEqual([[1], [2], [3]]);
    });

    it('should handle a left-skewed tree', async () => {
      const result = await service.solveLevelOrder(node(3, node(2, node(1))));
      expect(result).toEqual([[3], [2], [1]]);
    });

    it('should handle a complete binary tree of 4 levels', async () => {
      //            1
      //          /   \
      //        2       3
      //       / \     / \
      //      4   5   6   7
      const result = await service.solveLevelOrder(
        node(1,
          node(2, node(4), node(5)),
          node(3, node(6), node(7)),
        ),
      );
      expect(result).toEqual([[1], [2, 3], [4, 5, 6, 7]]);
    });

    it('should use default value=0 when node has no value', async () => {
      const n = new TreeNodeDto();
      expect(await service.solveLevelOrder(n)).toEqual([[0]]);
    });

    it('should throw TreeProcessingException when depth exceeds maxDepth (500)', async () => {
      let deep = node(501);
      for (let i = 500; i >= 1; i--) deep = node(i, deep);

      await expect(service.solveLevelOrder(deep)).rejects.toThrow(TreeProcessingException);
      await expect(service.solveLevelOrder(deep)).rejects.toThrow(
        /Tree depth exceeds security limits/,
      );
    });

    it('should succeed exactly at maxDepth (500 levels)', async () => {
      let deep = node(500);
      for (let i = 499; i >= 1; i--) deep = node(i, undefined, deep);

      const result = await service.solveLevelOrder(deep);
      expect(result).toHaveLength(500);
    });

    it('should throw TreeProcessingException when node count exceeds maxNodes', async () => {
      const smallService = new TreesService({
        get: (key: string, def: number) => (key === 'TREE_MAX_NODES' ? 3 : def),
      } as unknown as ConfigService);

      try {
        const tree = node(1, node(2), node(3, node(4), node(5)));
        await expect(smallService.solveLevelOrder(tree)).rejects.toThrow(
          /Tree node count exceeds security limits/,
        );
      } finally {
        await smallService.onModuleDestroy();
      }
    });
  });
});
