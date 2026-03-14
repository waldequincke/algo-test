import { Test, TestingModule } from '@nestjs/testing';
import { TreeProcessingException } from '../infrastructure/tree-processing.exception';
import { TreeNodeDto } from './dto/tree-node.dto';
import { TreesController } from './trees.controller';
import { TreesService } from './trees.service';

describe('TreesController (Worker Threads)', () => {
  let controller: TreesController;
  let service: jest.Mocked<TreesService>;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [TreesController],
      providers: [
        {
          provide: TreesService,
          useValue: { solveLevelOrder: jest.fn() },
        },
      ],
    }).compile();

    controller = module.get(TreesController);
    service = module.get(TreesService);
  });

  it('should delegate to TreesService and return its result', async () => {
    const root = new TreeNodeDto();
    const expected = [[1], [2, 3]];
    service.solveLevelOrder.mockResolvedValue(expected);

    expect(await controller.getLevelOrder(root)).toBe(expected);
    expect(service.solveLevelOrder).toHaveBeenCalledWith(root);
  });

  it('should propagate TreeProcessingException thrown by the service', async () => {
    service.solveLevelOrder.mockRejectedValue(
      new TreeProcessingException('Tree depth exceeds security limits (Max: 500)'),
    );

    await expect(controller.getLevelOrder(new TreeNodeDto())).rejects.toThrow(
      TreeProcessingException,
    );
  });
});
