import { Body, Controller, HttpCode, Post } from '@nestjs/common';
import { ApiOperation, ApiTags } from '@nestjs/swagger';
import { TreeNodeDto } from './dto/tree-node.dto';
import { TreesService } from './trees.service';

/**
 * REST endpoint — async: BFS runs on a worker thread, event loop stays free.
 *
 * The TimingInterceptor adds X-Runtime-Ms and X-Runtime-Nanoseconds headers
 * for direct comparison with the event-loop, Java and Kotlin benchmark results.
 */
@ApiTags('Tree Algorithms')
@Controller('api/v1/trees')
export class TreesController {
  constructor(private readonly treesService: TreesService) {}

  @Post('level-order')
  @HttpCode(200)
  @ApiOperation({
    summary: 'Level Order Traversal',
    description:
      'Returns a list of lists representing the level-order traversal of the input tree.',
  })
  async getLevelOrder(@Body() root: TreeNodeDto): Promise<number[][]> {
    return this.treesService.solveLevelOrder(root);
  }
}
